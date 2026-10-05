const fs = require('fs');
const html = fs.readFileSync('/home/sword/Documents/projects/marin/templates/marin_chat.html', 'utf8');
const scriptMatches = html.match(/<script>([\s\S]*?)<\/script>/gi);
let idx = 1;
for (const match of scriptMatches) {
    const code = match.replace(/<\/?script>/g, '');
    fs.writeFileSync(`test_${idx}.js`, code);
    idx++;
}
