import re

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "r") as f:
    html = f.read()

old_dir_match = """                if (chunk.includes('__DIRECTOR__')) {
                    const dirMatch = chunk.match(/__DIRECTOR__([A-Za-z0-9+\/=]+)__END__/);"""
new_dir_match = """                if (chunk.includes('__DIRECTOR__')) {
                    const dirMatch = chunk.match(/__DIRECTOR__([A-Za-z0-9+\/=\s]+)__END__/);"""
html = html.replace(old_dir_match, new_dir_match)

old_dir_replace = """                        chunk = chunk.replace(/__DIRECTOR__[A-Za-z0-9+\/=]+__END__/, '');"""
new_dir_replace = """                        chunk = chunk.replace(/__DIRECTOR__[A-Za-z0-9+\/=\s]+__END__/, '');"""
html = html.replace(old_dir_replace, new_dir_replace)

old_dir_global_replace = """                                      .replace(/__DIRECTOR__[A-Za-z0-9+\/=]*__END__/g, '')"""
new_dir_global_replace = """                                      .replace(/__DIRECTOR__[A-Za-z0-9+\/=\s]*(__END__)?/g, '')"""
html = html.replace(old_dir_global_replace, new_dir_global_replace)
html = html.replace("""                                     .replace(/__DIRECTOR__[A-Za-z0-9+\/=]*__END__/g, '')""", """                                     .replace(/__DIRECTOR__[A-Za-z0-9+\/=\s]*(__END__)?/g, '')""")
html = html.replace("""                        .replace(/__DIRECTOR__[A-Za-z0-9+\/=]*__END__/g, '')""", """                        .replace(/__DIRECTOR__[A-Za-z0-9+\/=\s]*(__END__)?/g, '')""")

with open("/home/sword/Documents/projects/marin/templates/marin_chat.html", "w") as f:
    f.write(html)
