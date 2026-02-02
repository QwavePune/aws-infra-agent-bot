import os
print("Checking for ANY API keys...")
found = False
for key in os.environ:
    if "KEY" in key or "TOKEN" in key or "SECRET" in key:
        print(f"Found: {key}")
        found = True
if not found:
    print("No obvious API keys found.")
