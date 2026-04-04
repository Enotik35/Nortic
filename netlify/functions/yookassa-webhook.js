const YOOKASSA_API_URL = "https://api.yookassa.ru/v3";

function json(statusCode, body) {
  return {
    statusCode,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

async function fetchYooKassaPayment(paymentId, shopId, secretKey) {
  const auth = Buffer.from(`${shopId}:${secretKey}`).toString("base64");
  const response = await fetch(`${YOOKASSA_API_URL}/payments/${paymentId}`, {
    method: "GET",
    headers: {
      Authorization: `Basic ${auth}`,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`YooKassa lookup failed: ${response.status} ${text}`);
  }

  return response.json();
}

async function activateOnBackend(paymentId, backendUrl, internalToken) {
  const response = await fetch(backendUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-internal-token": internalToken,
    },
    body: JSON.stringify({
      payment_id: paymentId,
      payment_provider: "yookassa_sbp",
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backend activation failed: ${response.status} ${text}`);
  }

  return response.json();
}

exports.handler = async function handler(event) {
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }

  const shopId = process.env.YOOKASSA_SHOP_ID;
  const secretKey = process.env.YOOKASSA_SECRET_KEY;
  const backendUrl = process.env.BACKEND_ACTIVATE_URL;
  const internalToken = process.env.INTERNAL_API_TOKEN;

  if (!shopId || !secretKey || !backendUrl || !internalToken) {
    return json(500, { error: "Missing required environment variables" });
  }

  let payload;
  try {
    payload = JSON.parse(event.body || "{}");
  } catch {
    return json(400, { error: "Invalid JSON" });
  }

  if (payload.event !== "payment.succeeded") {
    return json(200, { ok: true, skipped: true });
  }

  const paymentId = payload?.object?.id;
  if (!paymentId) {
    return json(400, { error: "Missing payment id" });
  }

  try {
    const payment = await fetchYooKassaPayment(paymentId, shopId, secretKey);
    if (payment.status !== "succeeded") {
      return json(200, { ok: true, skipped: true });
    }

    const activationResult = await activateOnBackend(paymentId, backendUrl, internalToken);
    return json(200, { ok: true, activation: activationResult });
  } catch (error) {
    return json(502, { error: error.message || "Webhook processing failed" });
  }
};
