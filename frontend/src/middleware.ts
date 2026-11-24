import { NextResponse, type NextRequest } from "next/server";

// UX-only guard: send visitors without a session cookie to /login. Real authorization
// is enforced by the backend on every API request.
const PUBLIC = new Set(["/login", "/signup", "/forgot-password", "/reset-password", "/accept-invite"]);

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  // The access cookie lives 15 minutes; the refresh cookie keeps the session alive longer.
  const hasSession = req.cookies.has("invoiceflow_session") || req.cookies.has("invoiceflow_refresh");
  // the legal pages (terms, privacy, data processing, accessibility, business details) must be readable by anyone
  if (!hasSession && !PUBLIC.has(pathname) && !pathname.startsWith("/legal")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|health|_next|favicon.ico|.*\\.(?:png|svg|ico|webp)).*)"],
};
