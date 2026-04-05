function html(statusCode, body) {
  return {
    statusCode,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
    body,
  };
}

exports.handler = async function handler() {
  return html(
    200,
    `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Оплата принята</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f6f2eb;
        --card: #fffdf9;
        --text: #1f1b16;
        --muted: #6a6257;
        --accent: #c96d2d;
        --border: #eadfce;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--text);
        background:
          radial-gradient(circle at top, rgba(201, 109, 45, 0.14), transparent 32%),
          linear-gradient(180deg, #fbf7f1 0%, var(--bg) 100%);
      }

      main {
        width: min(100%, 640px);
        padding: 32px;
        border: 1px solid var(--border);
        border-radius: 24px;
        background: var(--card);
        box-shadow: 0 18px 50px rgba(50, 36, 19, 0.08);
      }

      h1 {
        margin: 0 0 16px;
        font-size: clamp(32px, 6vw, 48px);
        line-height: 1.05;
      }

      p {
        margin: 0 0 14px;
        font-size: 18px;
        line-height: 1.6;
      }

      .muted {
        color: var(--muted);
      }

      strong {
        color: var(--accent);
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Оплата принята</h1>
      <p>Если webhook уже дошел, подписка активируется автоматически.</p>
      <p>Вернитесь в Telegram-бот и откройте свою подписку. Если статус еще не обновился, подождите несколько секунд и проверьте снова.</p>
      <p class="muted">Эту страницу можно просто закрыть.</p>
    </main>
  </body>
</html>`
  );
};
