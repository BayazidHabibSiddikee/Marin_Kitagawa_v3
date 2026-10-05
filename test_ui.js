const puppeteer = require('puppeteer-core');
const os = require('os');

(async () => {
    // find chromium
    const browser = await puppeteer.launch({ 
        executablePath: '/usr/sbin/chromium', // or google-chrome
        args: ['--no-sandbox'] 
    }).catch(async (e) => {
        return await puppeteer.launch({ 
            executablePath: '/usr/bin/google-chrome', 
            args: ['--no-sandbox'] 
        });
    });
    
    const page = await browser.newPage();
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', error => console.log('PAGE ERROR:', error.message));
    
    await page.goto('http://127.0.0.1:5069/');
    await new Promise(r => setTimeout(r, 2000));
    
    console.log("Opening settings...");
    await page.evaluate(() => {
        openSettings();
    });
    
    await new Promise(r => setTimeout(r, 1000));
    
    console.log("Clicking theme tab...");
    await page.evaluate(() => {
        switchSettingsTab('themes');
    });
    
    await new Promise(r => setTimeout(r, 1000));
    
    console.log("Clicking cyberpunk...");
    await page.evaluate(() => {
        applyTheme('Cyberpunk');
    });
    
    await new Promise(r => setTimeout(r, 1000));
    
    console.log("Saving settings...");
    await page.evaluate(() => {
        saveSettings();
    });
    
    await new Promise(r => setTimeout(r, 2000));
    
    await browser.close();
})();
