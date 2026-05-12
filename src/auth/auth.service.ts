import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  InternalServerErrorException,
  NotFoundException,
  UnauthorizedException,
} from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import { JwtService } from "@nestjs/jwt";
import * as bcrypt from "bcrypt";
import { randomBytes, randomInt } from "crypto";
import { MailService } from "../mail/mail.service";
import { UsersService } from "../users/users.service";
import { ChangePasswordDto } from "./dto/change-password.dto";
import { ForgotPasswordDto } from "./dto/forgot-password.dto";
import { LoginDto } from "./dto/login.dto";
import { RegisterDto } from "./dto/register.dto";
import { VerifyOtpDto } from "./dto/verify-otp.dto";

@Injectable()
export class AuthService {
  constructor(
    private readonly usersService: UsersService,
    private readonly jwtService: JwtService,
    private readonly configService: ConfigService,
    private readonly mailService: MailService,
  ) {}

  async register(dto: RegisterDto) {
    const existingEmail = await this.usersService.findByEmail(dto.email);
    if (existingEmail) {
      throw new ConflictException("Email already registered");
    }

    const existingPhone = await this.usersService.findByPhone(dto.phone);
    if (existingPhone) {
      throw new ConflictException("Phone already registered");
    }

    const passwordHash = await bcrypt.hash(dto.password, 10);
    const otp = this.generateOtp();
    const emailOtp = await bcrypt.hash(otp, 10);
    const emailOtpExpiresAt = new Date(Date.now() + 10 * 60 * 1000);

    const user = await this.usersService.createUser({
      name: dto.name,
      phone: dto.phone,
      email: dto.email.toLowerCase(),
      passwordHash,
      isEmailVerified: false,
      emailOtp,
      emailOtpExpiresAt,
    });

    try {
      await this.mailService.sendOtpEmail(dto.email, otp);
    } catch (error) {
      throw new InternalServerErrorException("Failed to send OTP email");
    }

    return {
      message: "User registered successfully. Please verify your email.",
      userId: user.id,
    };
  }

  async login(dto: LoginDto) {
    const user = await this.usersService.findByEmail(dto.email, true);
    if (!user) {
      throw new UnauthorizedException("Invalid email or password");
    }

    const isPasswordValid = await bcrypt.compare(
      dto.password,
      user.passwordHash,
    );
    if (!isPasswordValid) {
      throw new UnauthorizedException("Invalid email or password");
    }

    if (!user.isEmailVerified) {
      throw new ForbiddenException("Email is not verified");
    }

    const { accessToken, refreshToken } = await this.generateTokens(
      user.id,
      user.email,
    );
    const refreshTokenHash = await bcrypt.hash(refreshToken, 10);
    await this.usersService.setRefreshTokenHash(user.id, refreshTokenHash);

    return {
      accessToken,
      refreshToken,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        phone: user.phone,
      },
    };
  }

  async forgotPasswordEmail(dto: ForgotPasswordDto) {
    const user = await this.usersService.findByEmail(dto.email);
    if (!user) {
      return {
        message: "If the email exists, a new password has been sent.",
      };
    }

    const newPassword = this.generatePassword();
    const passwordHash = await bcrypt.hash(newPassword, 10);

    await this.usersService.updateById(user.id, {
      passwordHash,
      refreshTokenHash: null,
      resetPasswordTokenHash: null,
      resetPasswordExpiresAt: null,
    });

    try {
      await this.mailService.sendNewPasswordEmail(user.email, newPassword);
    } catch (error) {
      throw new InternalServerErrorException(
        "Failed to send new password email",
      );
    }

    return {
      message: "If the email exists, a new password has been sent.",
    };
  }

  async verifyOtp(dto: VerifyOtpDto) {
    const user = await this.usersService.findByEmail(dto.email, true);
    if (!user) {
      throw new BadRequestException("Invalid email");
    }

    if (!user.emailOtp) {
      throw new BadRequestException("OTP not found");
    }

    if (
      !user.emailOtpExpiresAt ||
      user.emailOtpExpiresAt.getTime() < Date.now()
    ) {
      throw new BadRequestException("OTP expired");
    }

    const otpMatches = await bcrypt.compare(dto.otp, user.emailOtp);
    if (!otpMatches) {
      throw new BadRequestException("Invalid OTP");
    }

    await this.usersService.updateById(user.id, {
      isEmailVerified: true,
      emailOtp: null,
      emailOtpExpiresAt: null,
    });

    return { message: "Email verified successfully" };
  }

  async changePassword(userId: string, dto: ChangePasswordDto) {
    const user = await this.usersService.findById(userId, true);
    if (!user) {
      throw new NotFoundException("User not found");
    }

    const isCurrentPasswordValid = await bcrypt.compare(
      dto.currentPassword,
      user.passwordHash,
    );
    if (!isCurrentPasswordValid) {
      throw new UnauthorizedException("Current password is incorrect");
    }

    const passwordHash = await bcrypt.hash(dto.newPassword, 10);
    await this.usersService.updateById(user.id, {
      passwordHash,
      refreshTokenHash: null,
    });

    return { message: "Password changed successfully" };
  }

  private async generateTokens(userId: string, email: string) {
    const payload = { sub: userId, email, type: "USER" };

    const accessToken = await this.jwtService.signAsync(payload, {
      secret:
        this.configService.get<string>("JWT_ACCESS_SECRET") ??
        "dev_access_secret",
      expiresIn:
        this.configService.get<string>("JWT_ACCESS_EXPIRES_IN") ?? "15m",
    });

    const refreshToken = await this.jwtService.signAsync(payload, {
      secret:
        this.configService.get<string>("JWT_REFRESH_SECRET") ??
        "dev_refresh_secret",
      expiresIn:
        this.configService.get<string>("JWT_REFRESH_EXPIRES_IN") ?? "7d",
    });

    return { accessToken, refreshToken };
  }

  private generateOtp(): string {
    return randomInt(0, 1000000).toString().padStart(6, "0");
  }

  private generatePassword(): string {
    return randomBytes(9).toString("base64url");
  }
}
