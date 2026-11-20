import { NextResponse, type NextRequest } from "next/server";

// UX-only guard: send visitors without a session cookie to /login. Real authorization
// is enforced by the backend on every API request.
export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const hasSession = req.cookies.has("invoiceflow_session");
  if (!hasSession && pathname !== "/login") {
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
