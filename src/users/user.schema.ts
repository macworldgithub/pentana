import { Prop, Schema, SchemaFactory } from "@nestjs/mongoose";
import { Document } from "mongoose";

export type UserDocument = User & Document;

@Schema({
  timestamps: true,
  toJSON: {
    transform: (_doc, ret) => {
      const retWithPassword = ret as { passwordHash?: string };
      delete retWithPassword.passwordHash;
      return ret;
    },
  },
})
export class User {
  @Prop({ required: true, trim: true })
  name!: string;

  @Prop({ required: true, unique: true, trim: true })
  phone!: string;

  @Prop({ required: true, unique: true, lowercase: true, trim: true })
  email!: string;

  @Prop({ required: true, select: false })
  passwordHash!: string;

  @Prop({ default: false })
  isEmailVerified!: boolean;

  @Prop({ type: String, default: null, select: false })
  refreshTokenHash!: string | null;

  @Prop({ type: String, default: null, select: false })
  resetPasswordTokenHash!: string | null;

  @Prop({ type: Date, default: null, select: false })
  resetPasswordExpiresAt!: Date | null;

  @Prop({ type: String, default: null, select: false })
  emailOtp!: string | null;

  @Prop({ type: Date, default: null, select: false })
  emailOtpExpiresAt!: Date | null;
}

export const UserSchema = SchemaFactory.createForClass(User);
