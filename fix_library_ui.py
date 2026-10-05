import re

with open("/home/sword/Documents/projects/marin/templates/library.html", "r") as f:
    html = f.read()

old_loop = """                    const chunk = decoder.decode(value, { stream: true });
                    if (chunk.includes('__VIBE__')) continue;
                    if (chunk.includes('__STRUCTURED__')) continue;
                    reply += chunk;
                    // Bug 1 fix: use .bubble (not .msg-text)
                    // Bug 2 fix: use DOMPurify.sanitize + marked.parse (not undefined formatReply)
                    bubble.innerHTML = DOMPurify.sanitize(marked.parse(reply));"""

new_loop = """                    const chunk = decoder.decode(value, { stream: true });
                    reply += chunk;
                    let displayReply = reply.replace(/__(VIBE|STRUCTURED|DIRECTOR|TALK_ON|TALK_OFF)__[A-Za-z0-9+/=\s]*(__END__)?/g, '');
                    bubble.innerHTML = DOMPurify.sanitize(marked.parse(displayReply));"""

html = html.replace(old_loop, new_loop)

with open("/home/sword/Documents/projects/marin/templates/library.html", "w") as f:
    f.write(html)
