const fs = require('fs');
const html = fs.readFileSync('templates/marin_chat.html', 'utf8');
const scriptMatch = html.match(/<script>(.*?)<\/script>/s);
if (scriptMatch) {
  try {
    new Function(scriptMatch[1]);
    console.log("No syntax errors!");
  } catch (e) {
    console.error("Syntax error:", e);
  }
}
