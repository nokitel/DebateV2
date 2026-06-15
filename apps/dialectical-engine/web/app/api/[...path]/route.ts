const COORDINATOR_URL = process.env.DIALECTICAL_COORDINATOR_URL || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

async function proxyApi(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const sourceUrl = new URL(request.url);
  const targetUrl = new URL(`/api/${path.join("/")}${sourceUrl.search}`, COORDINATOR_URL);
  const headers = new Headers(request.headers);
  headers.delete("host");

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

export function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyApi(request, context);
}

export function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyApi(request, context);
}

export function PUT(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyApi(request, context);
}

export function PATCH(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyApi(request, context);
}

export function DELETE(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyApi(request, context);
}
