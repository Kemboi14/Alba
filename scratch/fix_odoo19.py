import os
import re

def fix_odoo_19_compliance(root_dir):
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.xml') or file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r') as f:
                    content = f.read()
                
                original_content = content
                
                # 1. Replace <tree with <list (only if not followed by _ or part of a word)
                content = re.sub(r'<tree(\s|>)', r'<list\1', content)
                content = re.sub(r'</tree>', r'</list>', content)
                
                # 2. Replace type="tree" with type="list"
                content = content.replace('type="tree"', 'type="list"')
                
                # 3. Replace mode="tree" with mode="list"
                content = content.replace('mode="tree"', 'mode="list"')
                
                # 4. Replace view_mode="tree,form" with view_mode="list,form"
                content = content.replace('view_mode="tree,form"', 'view_mode="list,form"')
                content = content.replace('view_mode="tree,kanban,form"', 'view_mode="list,kanban,form"')
                content = content.replace('view_mode="kanban,tree,form"', 'view_mode="kanban,list,form"')
                
                # 5. Replace 'tree,form' with 'list,form' in Python
                content = content.replace("'tree,form'", "'list,form'")
                content = content.replace('"tree,form"', '"list,form"')
                
                # 6. Rename view IDs and names (best practice)
                # This might be risky if they are referenced elsewhere, but usually they are internal to the module
                # Let's be cautious and only rename common patterns
                content = content.replace('_tree"', '_list"')
                content = content.replace('.tree"', '.list"')
                
                if content != original_content:
                    print(f"Fixed {path}")
                    with open(path, 'w') as f:
                        f.write(content)

if __name__ == "__main__":
    fix_odoo_19_compliance("/home/nick/ACCT.f/odoo_addons")
