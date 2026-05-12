import { ValidationPipe } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import { getModelToken } from "@nestjs/mongoose";
import * as bcrypt from "bcrypt";
import { INestApplication } from "@nestjs/common";
import * as request from "supertest";
import { MongoMemoryServer } from "mongodb-memory-server";
import { Model } from "mongoose";
import { AppModule } from "../src/app.module";
import { MailService } from "../src/mail/mail.service";
import { User, UserDocument } from "../src/users/user.schema";

describe("Auth (e2e)", () => {
  let app: INestApplication;
  let mongo: MongoMemoryServer;
  let userModel: Model<UserDocument>;

  beforeAll(async () => {
    mongo = await MongoMemoryServer.create();
    process.env.MONGO_URI = mongo.getUri();
    process.env.MONGODB_URI = mongo.getUri();
    process.env.JWT_ACCESS_SECRET = "test_access_secret";
    process.env.JWT_REFRESH_SECRET = "test_refresh_secret";

    const moduleRef = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(MailService)
      .useValue({
        sendOtpEmail: jest.fn(),
        sendNewPasswordEmail: jest.fn(),
      })
      .compile();

    app = moduleRef.createNestApplication();
    app.setGlobalPrefix("api");
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
      }),
    );
    await app.init();

    userModel = moduleRef.get(getModelToken(User.name));
  });

  afterAll(async () => {
    await app.close();
    await mongo.stop();
  });

  it("registers, verifies, logs in, and changes password", async () => {
    const email = "test@example.com";
    const phone = "+15551234567";
    const password = "Password123";

    await request(app.getHttpServer())
      .post("/api/auth/register")
      .send({ name: "Test User", phone, email, password })
      .expect(201);

    const otp = "123456";
    const emailOtp = await bcrypt.hash(otp, 10);
    await userModel.updateOne(
      { email },
      { emailOtp, emailOtpExpiresAt: new Date(Date.now() + 10 * 60 * 1000) },
    );

    await request(app.getHttpServer())
      .post("/api/auth/verify-otp")
      .send({ email, otp })
      .expect(200);

    const loginResponse = await request(app.getHttpServer())
      .post("/api/auth/login")
      .send({ email, password })
      .expect(200);

    const accessToken = loginResponse.body.accessToken;

    await request(app.getHttpServer())
      .post("/api/auth/change-password")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({ currentPassword: password, newPassword: "NewPassword123" })
      .expect(200);
  });

  it("sends forgot password email without enumeration", async () => {
    await request(app.getHttpServer())
      .post("/api/auth/forgot-password-email")
      .send({ email: "test@example.com" })
      .expect(200);
  });
});
