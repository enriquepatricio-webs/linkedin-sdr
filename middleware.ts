import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, safeEqual, sessionToken } from "@/lib/auth";

export async function middleware(req: NextRequest) {
  if (!process.env.PANEL_PASSWORD) {
    return new NextResponse("Configura PANEL_PASSWORD en Vercel para proteger el panel.", { status: 503 });
  }
  const cookie = req.cookies.get(SESSION_COOKIE)?.value ?? "";
  if (cookie && safeEqual(cookie, await sessionToken())) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  // La API Python (/api/py) tiene su propia clave; el login y los estáticos quedan fuera.
  matcher: ["/((?!api/py|login|_next/static|_next/image|favicon.ico).*)"],
};
