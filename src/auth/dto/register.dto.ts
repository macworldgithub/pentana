import { ApiProperty } from "@nestjs/swagger";
import {
  IsEmail,
  IsNotEmpty,
  IsString,
  Matches,
  MinLength,
} from "class-validator";

export class RegisterDto {
  @IsString()
  @IsNotEmpty()
  @ApiProperty({ example: "Jane Doe" })
  name!: string;

  @IsString()
  @IsNotEmpty()
  @Matches(/^\+?[1-9]\d{1,14}$/)
  @ApiProperty({ example: "+15551234567" })
  phone!: string;

  @IsEmail()
  @ApiProperty({ example: "jane@example.com" })
  email!: string;

  @IsString()
  @MinLength(8)
  @ApiProperty({ example: "Password123" })
  password!: string;
}
