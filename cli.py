#!/usr/bin/env python3
"""
PyVault CLI
Secure, zero-knowledge password manager command-line interface.
With Emergency Recovery Key support.
"""

import sys
import getpass
import argparse
from typing import Optional
from core.models import Vault, VaultEntry, generate_password, copy_to_clipboard_timed

def get_vault_path() -> str:
    if os.environ.get("PYVAULT_PATH"):
        return os.environ["PYVAULT_PATH"]
    home_vault = os.path.expanduser("~/.pyvault/vault.enc")
    if os.path.exists(home_vault):
        return home_vault
    if os.path.exists("vault.enc"):
        return os.path.abspath("vault.enc")
    return home_vault

DEFAULT_VAULT_PATH = get_vault_path()


def prompt_password(prompt_text: str = "Enter Master Password: ") -> str:
    pw = getpass.getpass(prompt_text)
    if not pw:
        print("Error: Password cannot be empty.")
        sys.exit(1)
    return pw


def load_vault(vault_path: str = DEFAULT_VAULT_PATH) -> Vault:
    vault = Vault(vault_path)
    if not vault.exists:
        print(f"Vault '{vault_path}' does not exist.")
        print("Run 'python cli.py init' to create a new vault.")
        sys.exit(1)
    
    master_pw = prompt_password("Master Password: ")
    try:
        vault.unlock(master_pw)
    except ValueError as e:
        print(f"Error: {e}")
        print("Hint: Run 'python cli.py recover' if you forgot your Master Password.")
        sys.exit(1)
    return vault


def cmd_init(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = Vault(vault_path)
    if vault.exists:
        print(f"Error: Vault '{vault_path}' already exists.")
        sys.exit(1)

    print(f"\n=== Initializing New PyVault at '{vault_path}' ===")
    pw1 = prompt_password("Create Master Password: ")
    pw2 = prompt_password("Confirm Master Password: ")
    if pw1 != pw2:
        print("Error: Passwords do not match.")
        sys.exit(1)

    recovery_key = vault.initialize(pw1)
    print("\n" + "=" * 65)
    print("        ⚠️  YOUR EMERGENCY RECOVERY KEY  ⚠️        ")
    print("=" * 65)
    print(f"\n   {recovery_key}\n")
    print("-" * 65)
    print("IMPORTANT: Save or write down this key in a secure offline place.")
    print("If you ever forget your Master Password, this key is the ONLY")
    print("way to restore access to your vault.")
    print("=" * 65 + "\n")


def cmd_recover(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = Vault(vault_path)
    if not vault.exists:
        print(f"Vault '{vault_path}' does not exist.")
        sys.exit(1)

    print("\n=== Emergency Vault Recovery ===")
    key_input = input("Enter your Emergency Recovery Key: ").strip()
    if not key_input:
        print("Error: Recovery Key cannot be empty.")
        sys.exit(1)

    try:
        vault.recover(key_input)
    except ValueError as e:
        print(f"Recovery failed: {e}")
        sys.exit(1)

    print("\n[+] Recovery Key verified! Access restored.")
    new_pw1 = prompt_password("Create New Master Password: ")
    new_pw2 = prompt_password("Confirm New Master Password: ")
    if new_pw1 != new_pw2:
        print("Error: Passwords do not match.")
        sys.exit(1)

    vault.reset_master_password(new_pw1)
    print("[+] Master Password has been successfully reset!")


def cmd_add(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = load_vault(vault_path)

    title = args.title or input("Account / Service Title (e.g., GitHub): ").strip()
    if not title:
        print("Error: Title is required.")
        return

    existing = vault.get_by_title(title)
    if existing:
        print(f"Error: An entry with title '{title}' already exists. Use 'delete' or 'edit'.")
        return

    username = args.username or input("Username / Email: ").strip()
    
    password = args.password
    if not password:
        choice = input("Generate a strong random password? (Y/n): ").strip().lower()
        if choice in ("", "y", "yes"):
            password = generate_password(length=20)
            print(f"Generated Password: {password}")
        else:
            password = getpass.getpass("Enter Password: ")

    url = input("Website URL (optional): ").strip()
    notes = input("Notes (optional): ").strip()

    vault.add(title=title, username=username, password=password, url=url, notes=notes)
    vault.save()
    print(f"Entry '{title}' successfully saved!")


def cmd_get(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = load_vault(vault_path)

    title = args.title
    entry = vault.get_by_title(title)
    if not entry:
        matches = vault.search(title)
        if matches:
            print(f"No exact match for '{title}'. Did you mean:")
            for m in matches:
                print(f"  - {m.title} ({m.username})")
        else:
            print(f"No entry found matching '{title}'.")
        return

    print(f"\n--- {entry.title} ---")
    print(f"Username : {entry.username}")
    if entry.url:
        print(f"URL      : {entry.url}")
    if entry.notes:
        print(f"Notes    : {entry.notes}")

    copy_to_clipboard_timed(entry.password, timeout_seconds=20)
    print("\n[+] Password copied to clipboard! (Will auto-clear in 20 seconds)")
    
    if args.show:
        print(f"Password : {entry.password}")


def cmd_list(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = load_vault(vault_path)

    if not vault.entries:
        print("Vault is empty. Use 'python cli.py add' to add entries.")
        return

    print(f"\nSaved Accounts ({len(vault.entries)} entries):")
    print(f"{'TITLE':<25} {'USERNAME':<30} {'URL':<25}")
    print("-" * 80)
    for entry in sorted(vault.entries, key=lambda x: x.title.lower()):
        print(f"{entry.title:<25} {entry.username:<30} {entry.url:<25}")
    print()


def cmd_search(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = load_vault(vault_path)

    query = args.query
    results = vault.search(query)
    if not results:
        print(f"No entries found matching '{query}'.")
        return

    print(f"\nSearch results for '{query}' ({len(results)} matches):")
    print(f"{'TITLE':<25} {'USERNAME':<30} {'URL':<25}")
    print("-" * 80)
    for entry in sorted(results, key=lambda x: x.title.lower()):
        print(f"{entry.title:<25} {entry.username:<30} {entry.url:<25}")
    print()


def cmd_delete(args):
    vault_path = args.vault or DEFAULT_VAULT_PATH
    vault = load_vault(vault_path)

    title = args.title
    entry = vault.get_by_title(title)
    if not entry:
        print(f"Entry '{title}' not found.")
        return

    confirm = input(f"Are you sure you want to delete '{entry.title}'? (yes/N): ").strip().lower()
    if confirm == "yes":
        vault.delete(entry.id)
        vault.save()
        print(f"Entry '{title}' deleted.")
    else:
        print("Cancelled.")


def cmd_generate(args):
    pw = generate_password(
        length=args.length,
        use_symbols=not args.no_symbols,
        use_numbers=not args.no_numbers
    )
    print(f"Generated Password ({args.length} chars): {pw}")
    if args.copy:
        copy_to_clipboard_timed(pw, timeout_seconds=20)
        print("[+] Copied to clipboard for 20 seconds.")


def cmd_sync(args):
    from sync_server import run_sync_server
    vault_path = args.vault or DEFAULT_VAULT_PATH
    run_sync_server(vault_path=vault_path)


def main():
    parser = argparse.ArgumentParser(description="PyVault: Zero-Knowledge Secure Password Manager")
    parser.add_argument("--vault", "-v", default=DEFAULT_VAULT_PATH, help="Path to vault file (default: vault.enc)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Create a new vault")
    p_init.set_defaults(func=cmd_init)

    # recover
    p_rec = subparsers.add_parser("recover", help="Recover vault with Emergency Recovery Key")
    p_rec.set_defaults(func=cmd_recover)

    # add
    p_add = subparsers.add_parser("add", help="Add a new password entry")
    p_add.add_argument("title", nargs="?", help="Title/Name of account")
    p_add.add_argument("-u", "--username", help="Username or email")
    p_add.add_argument("-p", "--password", help="Password (omit to prompt or generate)")
    p_add.set_defaults(func=cmd_add)

    # get
    p_get = subparsers.add_parser("get", help="Get entry and copy password to clipboard")
    p_get.add_argument("title", help="Title of account to retrieve")
    p_get.add_argument("-s", "--show", action="store_true", help="Print password to terminal")
    p_get.set_defaults(func=cmd_get)

    # list
    p_list = subparsers.add_parser("list", help="List all accounts")
    p_list.set_defaults(func=cmd_list)

    # search
    p_search = subparsers.add_parser("search", help="Search accounts")
    p_search.add_argument("query", help="Keyword to search for")
    p_search.set_defaults(func=cmd_search)

    # delete
    p_del = subparsers.add_parser("delete", help="Delete an entry")
    p_del.add_argument("title", help="Title of account to delete")
    p_del.set_defaults(func=cmd_delete)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate a random password")
    p_gen.add_argument("-l", "--length", type=int, default=20, help="Password length (default: 20)")
    p_gen.add_argument("--no-symbols", action="store_true", help="Exclude symbols")
    p_gen.add_argument("--no-numbers", action="store_true", help="Exclude numbers")
    p_gen.add_argument("-c", "--copy", action="store_true", help="Copy generated password to clipboard")
    p_gen.set_defaults(func=cmd_generate)

    # sync
    p_sync = subparsers.add_parser("sync", help="Start local Wi-Fi sync server for Android")
    p_sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
