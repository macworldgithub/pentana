import { Module } from "@nestjs/common";
import { ConfigModule, ConfigService } from "@nestjs/config";
import { MongooseModule } from "@nestjs/mongoose";
import { AuthModule } from "./auth/auth.module";
import { MailModule } from "./mail/mail.module";
import { UsersModule } from "./users/users.module";

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    MongooseModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        uri:
          configService.get<string>("MONGO_URI") ??
          configService.get<string>("MONGODB_URI") ??
          "mongodb://localhost:27017/pentana",
      }),
    }),
    UsersModule,
    MailModule,
    AuthModule,
  ],
})
export class AppModule {}
