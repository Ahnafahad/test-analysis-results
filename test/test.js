const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

(async () => {
  try {
    // 1. Launch a headless browser
    const browser = await puppeteer.launch();
    const page = await browser.newPage();

    // 2. Listen for any console messages from the browser
    page.on('console', (msg) => {
      // Print them in Node's console with their type
      const msgType = msg.type().toUpperCase();
      console.log(`[BROWSER_CONSOLE] [${msgType}]`, msg.text());
    });

    // 3. Listen specifically for JavaScript errors/exceptions
    page.on('pageerror', (err) => {
      console.error(`[BROWSER_ERROR]`, err.toString());
    });

    // 4. Build the local file URL to your index.html
    const filePath = path.resolve(__dirname, 'index.html');
    const fileUrl = `file://${filePath}`;

    // 5. Navigate to the local index.html
    console.log(`Loading page: ${fileUrl}`);
    await page.goto(fileUrl, { waitUntil: 'networkidle0' });

    // 6. Wait a bit for everything to load
    // (In case your page has scripts that take a while)
    await page.waitForTimeout(2000);

    // 7. Optionally, you can do checks inside the page:
    const bodyContent = await page.evaluate(() => document.body.innerText);
    if (!bodyContent.includes('Navigation')) {
      console.warn('[TEST WARNING] Couldn’t find "Navigation" text in the page body. Check if the HTML loaded correctly.');
    }

    // 8. Close Browser
    await browser.close();
    console.log('[TEST RESULT] Page loaded, test completed successfully.');
  } catch (err) {
    console.error('[TEST ERROR]', err);
    process.exit(1); // exit with error code
  }
})();
