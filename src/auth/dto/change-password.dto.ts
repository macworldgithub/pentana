import { IsString, MinLength } from "class-validator";
import { ApiProperty } from "@nestjs/swagger";

export class ChangePasswordDto {
  @IsString()
  @ApiProperty({ example: "Password123" })
  currentPassword!: string;

  @IsString()
  @MinLength(8)
  @ApiProperty({ example: "NewPassword123" })
  newPassword!: string;
}
