import { ApiProperty } from "@nestjs/swagger";
import { IsEmail, IsString, MaxLength, MinLength } from "class-validator";

export class VerifyOtpDto {
  @IsEmail()
  @ApiProperty({ example: "jane@example.com" })
  email!: string;

  @IsString()
  @MinLength(6)
  @MaxLength(6)
  @ApiProperty({ example: "123456" })
  otp!: string;
}
