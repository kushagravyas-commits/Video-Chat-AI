"""
Agent CLI — Interactive Chat Interface for Video Chat Agent
Run this script to start chatting with the MasterAgent.

Usage:
    python agent_cli.py

Commands:
    quit / exit  — Exit the CLI
    clear        — Clear conversation history
    history      — Show conversation history
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

# Setup logging (minimal for CLI)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/agent_cli.log'),
        logging.StreamHandler()
    ]
)

# Suppress noisy loggers in CLI mode
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ============= COLORS =============

class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def print_banner():
    """Print welcome banner"""
    print(f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════════════════╗
║              🎬 Video Chat Agent — CLI                   ║
║     Powered by Gemini via OpenRouter + ChromaDB          ║
╚══════════════════════════════════════════════════════════╝{Colors.RESET}

{Colors.DIM}Commands:{Colors.RESET}
  {Colors.YELLOW}exit{Colors.RESET} / {Colors.YELLOW}quit{Colors.RESET}  — Leave the chat
  {Colors.YELLOW}clear{Colors.RESET}         — Reset conversation
  {Colors.YELLOW}history{Colors.RESET}       — Show message history

{Colors.DIM}Tips:{Colors.RESET}
  • Paste a YouTube URL to process a new video
  • Ask questions about processed videos
  • Request video trimming or highlight clips

{Colors.DIM}{'─' * 58}{Colors.RESET}
""")


def print_history(messages):
    """Print conversation history (excluding system prompt)"""
    print(f"\n{Colors.YELLOW}{'─' * 40} History {'─' * 40}{Colors.RESET}")
    for msg in messages:
        role = msg.get('role', '')
        content = msg.get('content', '')

        if role == 'system':
            continue
        elif role == 'user':
            print(f"  {Colors.GREEN}You:{Colors.RESET} {content[:120]}{'...' if len(content) > 120 else ''}")
        elif role == 'assistant':
            if msg.get('tool_calls'):
                tools = [tc['function']['name'] for tc in msg['tool_calls']]
                print(f"  {Colors.MAGENTA}Agent → Tools:{Colors.RESET} {', '.join(tools)}")
            elif content:
                preview = content[:120].replace('\n', ' ')
                print(f"  {Colors.CYAN}Agent:{Colors.RESET} {preview}{'...' if len(content) > 120 else ''}")
        elif role == 'tool':
            pass  # Skip tool results in history view

    print(f"{Colors.YELLOW}{'─' * 89}{Colors.RESET}\n")


def main():
    """Main CLI loop"""
    os.makedirs('logs', exist_ok=True)

    print_banner()

    # Initialize agent
    print(f"{Colors.DIM}Initializing agent...{Colors.RESET}", end=" ", flush=True)
    try:
        from modules.agent import MasterAgent
        agent = MasterAgent()
        print(f"{Colors.GREEN}Ready!{Colors.RESET}\n")
    except Exception as e:
        print(f"\n{Colors.RED}Failed to initialize agent: {e}{Colors.RESET}")
        sys.exit(1)

    # Chat loop
    while True:
        try:
            # Get user input
            user_input = input(f"{Colors.GREEN}{Colors.BOLD}You: {Colors.RESET}").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ('exit', 'quit', 'q'):
                print(f"\n{Colors.CYAN}Goodbye! 👋{Colors.RESET}\n")
                break

            if user_input.lower() == 'clear':
                agent.clear_conversation()
                print(f"{Colors.YELLOW}Conversation cleared.{Colors.RESET}\n")
                continue

            if user_input.lower() == 'history':
                print_history(agent.messages)
                continue

            # Process through agent
            print(f"\n{Colors.DIM}Thinking...{Colors.RESET}", flush=True)
            response = agent.chat(user_input)

            # Display response
            print(f"\n{Colors.CYAN}{Colors.BOLD}Agent:{Colors.RESET} {response}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.CYAN}Goodbye! 👋{Colors.RESET}\n")
            break
        except EOFError:
            print(f"\n\n{Colors.CYAN}Goodbye! 👋{Colors.RESET}\n")
            break
        except Exception as e:
            print(f"\n{Colors.RED}Error: {e}{Colors.RESET}\n")
            logger.error(f"CLI error: {e}", exc_info=True)


if __name__ == '__main__':
    main()
