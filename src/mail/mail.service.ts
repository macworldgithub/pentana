import { Injectable } from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import * as nodemailer from "nodemailer";

@Injectable()
export class MailService {
  private transporter: nodemailer.Transporter;

  constructor(private readonly configService: ConfigService) {
    const host = this.configService.get<string>("SMTP_HOST");
    const port = Number(this.configService.get<string>("SMTP_PORT") ?? "587");
    const secure = this.configService.get<string>("SMTP_SECURE") === "true";
    const user = this.configService.get<string>("SMTP_USER");
    const pass = this.configService.get<string>("SMTP_PASS");

    this.transporter = nodemailer.createTransport({
      host,
      port,
      secure,
      auth: user && pass ? { user, pass } : undefined,
    });
  }

  async sendOtpEmail(to: string, otp: string): Promise<void> {
    await this.transporter.sendMail({
      to,
      subject: "Your verification code",
      text: `Your verification code is ${otp}`,
    });
  }

  async sendNewPasswordEmail(to: string, newPassword: string): Promise<void> {
    await this.transporter.sendMail({
      to,
      subject: "Your new password",
      text: `Your new password is ${newPassword}`,
    });
  }
}
