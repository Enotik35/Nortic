function response(statusCode, body, headers = {}) {
  return {
    statusCode,
    headers,
    body,
  };
}

function buildForwardHeaders(upstreamHeaders) {
  const forwarded = {};
  const allowedHeaders = [
    "content-type",
    "cache-control",
    "content-disposition",
    "profile-title",
    "profile-update-interval",
    "profile-web-page-url",
    "support-url",
    "announce",
    "subscription-userinfo",
  ];

  for (const headerName of allowedHeaders) {
    const value = upstreamHeaders.get(headerName);
    if (value) {
      forwarded[headerName] = value;
    }
  }

  forwarded["x-subscription-proxy"] = "netlify";
  return forwarded;
}

exports.handler = async function handler(event) {
  const backendBaseUrl = process.env.BACKEND_BASE_URL;
  if (!backendBaseUrl) {
    return response(500, "Missing BACKEND_BASE_URL", {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
    });
  }

  const requestPath = event.path || "/";
  const query = event.rawQuery ? `?${event.rawQuery}` : "";
  const targetUrl = `${backendBaseUrl.replace(/\/$/, "")}${requestPath}${query}`;

  try {
    const upstream = await fetch(targetUrl, {
      method: "GET",
      headers: {
        accept: "text/plain, application/json;q=0.9, */*;q=0.8",
      },
    });

    const body = await upstream.text();
    return response(upstream.status, body, buildForwardHeaders(upstream.headers));
  } catch (error) {
    return response(502, error.message || "Subscription proxy failed", {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "no-store",
    });
  }
};
