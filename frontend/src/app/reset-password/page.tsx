"use client";

import { Suspense } from "react";
import { SetPasswordForm } from "@/components/set-password-form";

export default function ResetPasswordPage() {
  return <Suspense><SetPasswordForm mode="reset" /></Suspense>;
}
