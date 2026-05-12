import { Injectable } from "@nestjs/common";
import { InjectModel } from "@nestjs/mongoose";
import { Model } from "mongoose";
import { User, UserDocument } from "./user.schema";

@Injectable()
export class UsersService {
  constructor(
    @InjectModel(User.name) private readonly userModel: Model<UserDocument>,
  ) {}

  async createUser(data: Partial<User>): Promise<UserDocument> {
    const createdUser = new this.userModel(data);
    return createdUser.save();
  }

  async findByEmail(
    email: string,
    includeSensitive = false,
  ): Promise<UserDocument | null> {
    const query = this.userModel.findOne({ email: email.toLowerCase() });
    if (includeSensitive) {
      query.select(
        "+passwordHash +refreshTokenHash +emailOtp +emailOtpExpiresAt +resetPasswordTokenHash +resetPasswordExpiresAt",
      );
    }
    return query.exec();
  }

  async findByPhone(phone: string): Promise<UserDocument | null> {
    return this.userModel.findOne({ phone }).exec();
  }

  async findById(
    userId: string,
    includeSensitive = false,
  ): Promise<UserDocument | null> {
    const query = this.userModel.findById(userId);
    if (includeSensitive) {
      query.select(
        "+passwordHash +refreshTokenHash +emailOtp +emailOtpExpiresAt +resetPasswordTokenHash +resetPasswordExpiresAt",
      );
    }
    return query.exec();
  }

  async updateById(
    userId: string,
    update: Partial<User>,
  ): Promise<UserDocument | null> {
    return this.userModel
      .findByIdAndUpdate(userId, update, { new: true })
      .exec();
  }

  async setRefreshTokenHash(
    userId: string,
    refreshTokenHash: string | null,
  ): Promise<void> {
    await this.userModel.findByIdAndUpdate(userId, { refreshTokenHash }).exec();
  }
}
