import { ApiProperty } from "@nestjs/swagger";
import { IsEmail, IsString, MinLength } from "class-validator";

export class LoginDto {
  @IsEmail()
  @ApiProperty({ example: "jane@example.com" })
  email!: string;

  @IsString()
  @MinLength(8)
  @ApiProperty({ example: "Password123" })
  password!: string;
}
