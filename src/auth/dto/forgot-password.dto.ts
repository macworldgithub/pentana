import { ApiProperty } from "@nestjs/swagger";
import { IsEmail } from "class-validator";

export class ForgotPasswordDto {
  @IsEmail()
  @ApiProperty({ example: "jane@example.com" })
  email!: string;
}
