"""
MasterAgent — Agentic Orchestrator for Video Chat
Uses OpenAI function calling via OpenRouter to decide which tools to invoke.
Maintains conversation memory across turns.
"""

import os
import json
import logging
import re
from typing import Dict, List, Optional
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

from models.sqlite_store import SQLiteStore

load_dotenv()
logger = logging.getLogger(__name__)

# ============= TOOL SCHEMAS (OpenAI function calling format) =============

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_video_exists",
            "description": "Check if a YouTube video's embeddings already exist in ChromaDB. Use this FIRST when a user provides a YouTube URL, to avoid re-processing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "The YouTube video ID (e.g. 'dQw4w9WgXcQ' from a YouTube URL). Extract this from the URL."
                    }
                },
                "required": ["video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "download_youtube_video",
            "description": "Download a YouTube video to local storage. Returns the video file path and metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "youtube_url": {
                        "type": "string",
                        "description": "Full YouTube URL (e.g. 'https://www.youtube.com/watch?v=...')"
                    }
                },
                "required": ["youtube_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_audio",
            "description": "Extract audio (MP3) from a video file. Required before transcription.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Path to the video file on disk"
                    }
                },
                "required": ["video_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_audio",
            "description": "Transcribe an audio file to text using Whisper. Returns transcript with timestamps and segments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "audio_path": {
                        "type": "string",
                        "description": "Path to the audio file (MP3)"
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code or 'auto' for automatic detection. Auto-detects language and translates non-English to English. Default: 'auto'",
                        "default": "auto"
                    }
                },
                "required": ["audio_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_and_store_embeddings",
            "description": "Generate embeddings for a transcript and store them in ChromaDB for RAG retrieval. Call this after transcription. The transcript is automatically retrieved from the session — you only need to provide the video_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video identifier (used as the key in ChromaDB)"
                    }
                },
                "required": ["video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_video_context",
            "description": "Search ChromaDB for relevant video segments matching a query. Use this to find context before answering questions about a video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video identifier to search within"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. user's question about the video)"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["video_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_processed_videos",
            "description": "List all videos that have been processed and have embeddings in ChromaDB.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trim_video",
            "description": "Trim a video to a specific time range. Creates a new clip file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Path to the source video file"
                    },
                    "start_seconds": {
                        "type": "number",
                        "description": "Start time in seconds"
                    },
                    "end_seconds": {
                        "type": "number",
                        "description": "End time in seconds"
                    },
                    "output_name": {
                        "type": "string",
                        "description": "Optional output filename (auto-generated if not provided)"
                    }
                },
                "required": ["video_path", "start_seconds", "end_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_highlight_clip",
            "description": "Create and RENDER a permanent highlight reel MP4 file by combining multiple video segments. Use this when the user asks for 'highlights', 'a highlight reel', or 'a summary video'. Returns the disk path to the rendered video file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "Path to the source video file on disk. If omitted, uses the last downloaded/processed video."
                    },
                    "segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start_seconds": {"type": "number", "description": "Start of segment in seconds"},
                                "end_seconds": {"type": "number", "description": "End of segment in seconds"}
                            },
                            "required": ["start_seconds", "end_seconds"]
                        },
                        "description": "List of time segments to include. Decide these based on actual video timestamps from the search context."
                    },
                    "output_name": {
                        "type": "string",
                        "description": "Optional output filename without .mp4 extension (e.g. 'VideoTitle_highlight_1'). The .mp4 extension is added automatically."
                    }
                },
                "required": ["segments"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_mentions_in_video",
            "description": "Find and count mentions in video(s) using HYBRID search (keyword regex + AI semantic). Works for everything: single words ('India', 'Trump'), phrases ('Iran and India friendship'), or concepts ('where Modi talked about the war'). Always use this for any 'how many times', 'count mentions', 'find mentions' queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of video IDs to search in"
                    },
                    "search_query": {
                        "type": "string",
                        "description": "What to search for. Can be a word ('India'), name ('Aditya Dhar'), phrase ('Iran and India friendship'), or concept ('praised the director')."
                    }
                },
                "required": ["video_ids", "search_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "index_video_visuals",
            "description": "Index a video's visual content for image search. Extracts keyframes and generates visual embeddings using NVIDIA Nemotron VL. Call this after generate_and_store_embeddings to enable visual search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video ID to index visually"
                    }
                },
                "required": ["video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_image_context_from_video",
            "description": "Search for visual content SHOWN in video(s). Finds scenes matching a text description by searching visual embeddings. Use for questions about what was SHOWN/DISPLAYED/APPEARED in the video, charts, graphics, scenes, people, locations, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Video IDs to search in"
                    },
                    "query": {
                        "type": "string",
                        "description": "Text description of what to find visually (e.g., 'a chart showing GDP growth', 'person at podium', 'map of India')"
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of results to return"
                    }
                },
                "required": ["video_ids", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_clips_from_mentions",
            "description": "Create video clips from mention timestamps. Supports smart grouping of nearby mentions and customizable clip duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video ID to create clips from"
                    },
                    "mentions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "description": "Mention object with start_time, end_time, text, etc."
                        },
                        "description": "List of mentions (from count_mentions_in_video result)"
                    },
                    "clip_duration_before": {
                        "type": "number",
                        "default": 2.0,
                        "description": "Seconds to include BEFORE mention starts (default: 2s)"
                    },
                    "clip_duration_after": {
                        "type": "number",
                        "default": 3.0,
                        "description": "Seconds to include AFTER mention ends (default: 3s)"
                    },
                    "expansion_mode": {
                        "type": "string",
                        "enum": ["default", "semantic", "ai_director"],
                        "default": "default",
                        "description": "Use 'semantic' to auto-align to sentences, 'ai_director' to use LLM to find the best viral hook, or 'default' to use fixed duration."
                    },
                    "smart_grouping": {
                        "type": "boolean",
                        "default": False,
                        "description": "Group nearby mentions into single clips (default: False = separate clips)"
                    },
                    "grouping_threshold_seconds": {
                        "type": "number",
                        "default": 7.0,
                        "description": "Group mentions within this many seconds (default: 7s)"
                    }
                },
                "required": ["video_id", "mentions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_viral_short",
            "description": "Dynamic Story Mode: Automatically finds the best mention of a topic, uses AI Director to clip it perfectly, and generates catchy titles for social media.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Video ID to search and clip from"
                    },
                    "topic": {
                        "type": "string",
                        "description": "The topic or person to search for (e.g., 'Bangladesh', 'Economy')"
                    }
                },
                "required": ["video_id", "topic"]
            }
        }
    }
]

# ============= SYSTEM PROMPT =============

SYSTEM_PROMPT = """You are an intelligent Video Chat Assistant powered by AI. You help users process, analyze, and interact with video content.

## CRITICAL: VIDEO AVAILABILITY CHECK
**ALWAYS do this FIRST for every user message:**
1. Check if `reference_video_ids` exist and are NON-EMPTY in your session data
2. **IF YES (Reference videos selected)**:
   - Use `search_video_context` to answer questions about these reference videos
   - If user message ALSO contains a YouTube URL: Process the new URL IN ADDITION to existing reference videos
   - Never ask "Please provide a YouTube URL" - the videos are already set up!
3. **IF NO (No reference videos selected)**: Only then check if the user message contains a YouTube URL
   - If URL found: Download and process it
   - If NO URL and NO reference videos: Ask the user to "Add a reference video or paste a YouTube URL"

**IMPORTANT: Session Behavior**
- When ALL reference videos are removed/deselected on the frontend, `reference_video_ids` will be an empty list `[]`
- Treat empty list the same as having no reference videos
- Don't re-mention old videos that were previously selected if they're no longer in reference_video_ids

## Your Capabilities:
1. **Process YouTube videos**: Download, extract audio, transcribe, generate text embeddings, and index visual keyframes.
2. **Answer questions**: Search video context (text + visual) and provide detailed answers with timestamps.
   - Search across MULTIPLE reference videos simultaneously for comparative analysis!
3. **Video Editing**: Trim clips (`trim_video`) and create highlight reels (`create_highlight_clip`). These tools RENDER real MP4 files.
4. **Manage videos**: List processed videos, check if a video exists.

## Workflow Orchestration:
- When a user provides a YouTube URL, **FIRST** use `download_youtube_video` (it has built-in check).
- If the tool returns `"status": "already_exists"`, the video is FULLY PROCESSED AND READY. Tell the user the video is ready and you can answer questions. DO NOT call transcribe_audio or generate_and_store_embeddings!
- If the tool returns `"status": "success"`, the video was just downloaded. Continue with `extract_audio` → `transcribe_audio` → `generate_and_store_embeddings` (this automatically generates text + visual embeddings).
- **CRITICAL**: Never call transcribe_audio or generate_and_store_embeddings if the download returned "already_exists".

## Searching Video Content:
CRITICAL: For ANY question about the video, you MUST call BOTH search tools:
1. `search_video_context` — searches what was SAID (transcript text)
2. `search_image_context_from_video` — searches what was SHOWN (visual frames)

ALWAYS call BOTH tools for EVERY question. Combine results in your answer.
Label each result source: "[Transcript]" or "[Visual]".
NEVER call only one — the user expects answers from both text AND visual content.

## Multi-Video Search:
- The system NOW SUPPORTS searching across MULTIPLE reference videos at once!
- When searching for context, the agent automatically searches ALL reference videos and returns the most relevant results from any of them.
- Results include the video title/ID so you know which video each result came from.
- This enables comparative analysis: "Compare how both videos discuss this topic" or "Find mentions of X across all videos".

## Context & Memory:
- **IMPORTANT**: When a user says "this video", "the video", or "it", refer to the currently active/selected video or the first reference video if multiple are selected.
- You CAN and SHOULD provide video IDs and Titles when asked. Use `list_processed_videos` to see what's available.
- Reference videos are stored in `session_data['reference_video_ids']` and are automatically used when searching context.

## Video IDs:
- ALWAYS use `youtube_<youtube_id>` for YouTube videos (e.g. `youtube_sZ9hmR8jiCY`).

## Highlights:
- When asked for "highlights", "summary clip", or "best parts", you MUST:
  1. Search context for key moments and identify different topics/themes.
  2. For EACH highlight (at least 2-3), decide on start/end times from actual video timestamps (e.g., "45s to 120s", "250s to 380s").
  3. Call `create_highlight_clip` SEPARATELY for EACH highlight:
     - Do NOT pass video_path - it will automatically use the last processed video
     - Pass output_name: "{video_title}_highlight_{number}" (e.g., "Taliban_Conflict_highlight_1" - NO .mp4)
     - Pass segments with actual timestamps from the context
  4. Create truly DIFFERENT highlights - don't overlap segments, use distinct timestamps for each.
  5. Do NOT just give text; the user wants actual rendered video files for each highlight.

## Mention Counting & Analysis

Use `count_mentions_in_video` for ALL mention/counting queries. It runs HYBRID search (keyword regex + AI semantic) automatically.

Works for everything:
- Single words: "India", "Trump", "propaganda"
- Names: "Aditya Dhar", "Dhruv Rathee"
- Phrases: "Iran and India friendship"
- Concepts: "praised the director", "called it propaganda"

CRITICAL: NEVER guess or use `search_video_context` for "how many times" questions. ALWAYS call `count_mentions_in_video`.
IMPORTANT: Do NOT auto-create clips. Only count and report.

### After Getting Mention Results:
The tool result contains a `display_json` field. You MUST output it EXACTLY as-is. Do NOT rephrase, summarize, or reformat.

YOUR RESPONSE MUST BE:
1. Copy-paste the `display_json` field from the tool result (the ```json ... ``` block)
2. Then on a new line: "Would you like me to create video clips for any of these mentions?"

FORBIDDEN:
- Do NOT write "X was mentioned N times" or any text summary
- Do NOT list mentions as bullet points or numbered lists
- Do NOT create your own tables or formatted text
- Do NOT add commentary before or after the JSON block
- ONLY output the `display_json` block + the clip question

**NEVER auto-create clips** - Wait for user to ask

### Example Flow:
User: "How many times is Israel mentioned in the video?"
You: Call count_mentions_in_video(video_ids=['youtube_xxx'], search_query='Israel')
Result: 15 mentions at timestamps 0:45, 2:30, 5:15, ...
You: Display results with table, timeline, and stats
You: Ask: "Would you like me to create video clips for each mention?"

## Clip Generation Workflow (Phase 2)

When user wants to create clips from mentions:

### CRITICAL: Always Ask Permission First
1. User asks about creating clips ("Can you make clips?", "Create clips for these mentions")
2. Show the mentions and ask: "Found X mentions. Would you like me to create video clips for these?"
3. **NEVER auto-create clips** - Always wait for explicit "Yes"

### Preference Collection Flow (STRICT UI ENFORCEMENT)
The UI handles the collection of clip preferences using a special interactive card. You MUST NOT try to ask the user these questions conversationally. 

When you ask "Would you like me to create video clips for any of these mentions?" (or the user asks up-front), you MUST include the following JSON block EXACTLY as shown. The frontend will intercept this JSON and render a beautiful form with buttons for the user to click.

Output this EXACT JSON format:
```json
{
  "type": "clip_options",
  "data": {
    "total_mentions": X
  }
}
```
Replace X with the total number of mentions found.

**CRITICAL RULE:** DO NOT output any other text explaining the options. The UI handles EVERYTHING.

### Handling UI Button Clicks
When the user clicks the "Generate Clips" button on the UI card, the frontend will send you a hidden message starting with `[SYSTEM COMMAND EXECUTED BY USER UI]`. 

For example:
`[SYSTEM COMMAND EXECUTED BY USER UI]\nAction: Extract top 5 mentions into clips.\nGrouping: true\nStyle: ai_director\nProceed immediately with "create_clips_from_mentions" without asking any questions.`

When you receive a `[SYSTEM COMMAND EXECUTED BY USER UI]`, you MUST IMMEDIATELY call the `create_clips_from_mentions` tool using the EXACT settings provided in the command. DO NOT ask for confirmation. DO NOT say "Okay, I will do that." Just execute the tool call instantly.


### Calling create_clips_from_mentions

After collecting preferences, call the tool with:
```
create_clips_from_mentions(
  video_id="youtube_xxx",
  mentions=[...mention list from count_mentions...],
  expansion_mode="semantic" | "ai_director" | "default", # Use selected option from Q2
  clip_duration_before=X,  # Optional if semantic/ai
  clip_duration_after=Y,   # Optional if semantic/ai
  smart_grouping=True/False,
  grouping_threshold_seconds=Z
)
```

### Dynamic Story Mode (Automated Shorts)

If the user wants you to completely automate the process of finding the best clip for a specific topic, you can use the `generate_viral_short` tool.
- Tell the user: "I will scan the video for the best discussion about {topic}, use the Viral AI Director to cut the perfect 15-60 second Short, and generate some catchy titles for you!"
- Call `generate_viral_short(video_id="...", topic="...")`. It will return the rendered clip and suggested titles.
- Show the results to the user.

### After Creating Clips
CRITICAL: You must format the final output as a clean, readable Markdown list. 
DO NOT put everything into one giant paragraph. Use line breaks.
DO NOT put a space between the brackets and parentheses in markdown links.

Example Format:
"Created 2 clips for you!

1. **Clip 1** - *Duration:* 21.5s - *Size:* 1.2 MB
   [Download Clip 1](/storage/clips/filename1.mp4)
   
2. **Clip 2** - *Duration:* 25.0s - *Size:* 1.5 MB
   [Download Clip 2](/storage/clips/filename2.mp4)"

Ask if the user wants to perform any other actions.

### Important Notes
- Full quality rendering (FFmpeg -crf 18, high quality)
- All clips kept permanently in storage/clips/
- Metadata saved automatically
- Never delete clips automatically (user keeps full control)
"""


class MasterAgent:
    """
    Agentic orchestrator that uses LLM tool-calling to manage the video pipeline.
    Maintains conversation history for multi-turn interactions.
    """

    def __init__(self, api_key: Optional[str] = None, callback=None, chroma_store=None):
        """Initialize the MasterAgent with all tool modules.

        Args:
            api_key: OpenRouter API key
            callback: Streaming callback for status/results
            chroma_store: Shared ChromaStore instance (avoids duplicate PersistentClient)
        """

        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        self.model = "openai/gpt-4o-mini"

        if not self.api_key:
            logger.error("OPENROUTER_API_KEY not found in environment")
            raise ValueError("OPENROUTER_API_KEY is required")

        # Initialize OpenAI client with OpenRouter
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        self.callback = callback  # Callback for streaming status/results

        # Initialize tool modules
        from modules.video_processor import VideoProcessor
        from modules.transcriber import Transcriber
        from modules.rag_processor import RAGProcessor
        from models.chroma_store import ChromaStore
        from models.sqlite_store import SQLiteStore
        from modules.video_tools import VideoTools

        self.video_processor = VideoProcessor(storage_dir="./storage")
        self.transcriber = Transcriber(model_name="base")
        self.rag_processor = RAGProcessor(api_key=self.api_key)
        # Use shared ChromaStore if provided, otherwise create new one
        self.chroma_store = chroma_store or ChromaStore(persist_dir=os.getenv('CHROMA_PERSIST_DIR', './chroma_data'))
        self.sqlite_store = SQLiteStore(db_path="./storage/database.sqlite")
        self.video_tools = VideoTools(output_dir="./storage/clips")

        # Initialize OpenRouter embedder for semantic search (Qwen3 + NVIDIA Nemotron)
        try:
            from modules.openrouter_embedder import OpenRouterEmbedder
            self.openrouter_embedder = OpenRouterEmbedder(api_key=self.api_key)
            logger.info("OpenRouterEmbedder initialized for semantic search")
        except Exception as e:
            logger.warning(f"OpenRouterEmbedder not available: {e}. Semantic search will fall back to v1.")
            self.openrouter_embedder = None

        # Conversation memory
        self.messages: List[Dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Track processed videos in this session (path mappings)
        self.session_data: Dict = {
            'highlight_counter': 0  # Counter for naming multiple highlights
        }

        logger.info("MasterAgent initialized with all tools")

    def clear_conversation(self):
        """Reset conversation history (keep system prompt and video context)"""
        # Preserve video context for continuous work on the same video
        preserved_context = {
            'last_video_path': self.session_data.get('last_video_path'),
            'last_video_id': self.session_data.get('last_video_id'),
            'last_metadata': self.session_data.get('last_metadata'),
            'reference_video_ids': self.session_data.get('reference_video_ids', []),
            'highlight_counter': 0
        }

        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.session_data = preserved_context
        logger.info("Conversation history cleared (video context preserved)")

    def chat(self, user_message: str) -> str:
        """
        Process a user message through the agentic loop.

        1. Add user message to history
        2. Call LLM with tools
        3. If LLM returns tool_calls, execute them and feed results back
        4. Repeat until LLM returns a final text response

        Args:
            user_message: The user's input

        Returns:
            The agent's final text response
        """
        # Inject reference video context so LLM can see it
        reference_video_ids = self.session_data.get('reference_video_ids', [])
        if reference_video_ids:
            video_context = f"[AVAILABLE REFERENCE VIDEOS: {', '.join(reference_video_ids)}. These videos are already processed and ready. Use search_video_context to answer questions about them. Do NOT ask for a URL.]\n\n{user_message}"
        else:
            video_context = user_message

        # Add user message to conversation
        self.messages.append({"role": "user", "content": video_context})

        max_iterations = 15  # Safety limit for tool-calling loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent loop iteration {iteration}")

            # Generate response from OpenAI
            try:
                if self.callback:
                    self.callback({"type": "status", "content": "Thinking..."})

                response = self.client.chat.completions.create(
                    model="openai/gpt-4o-mini",
                    messages=self.messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=4000,
                    extra_headers={
                        "HTTP-Referer": "http://localhost:5000",
                        "X-OpenRouter-Title": "Video Chat Agent"
                    }
                )
            except Exception as e:
                logger.error(f"OpenRouter API error: {str(e)}")
                error_msg = f"I encountered an error: {str(e)}. Please try again."
                if self.callback:
                    self.callback({"type": "error", "content": error_msg})
                self.messages.append({"role": "assistant", "content": error_msg})
                return error_msg

            choice = response.choices[0]
            message = choice.message

            # Case 1: LLM wants to call one or more tools
            if message.tool_calls:
                # Add assistant's tool-calling message to history
                self.messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                # Execute each tool call
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    logger.info(f"Executing tool: {func_name}({args})")
                    
                    if self.callback:
                        self.callback({
                            "type": "tool_start",
                            "tool": func_name,
                            "args": args
                        })

                    result = self._execute_tool(func_name, args)

                    # Save visual findings for injection into final response
                    if func_name == "search_image_context_from_video" and result.get('answer_summary'):
                        self.session_data['pending_visual_answer'] = result['answer_summary']

                    if self.callback:
                        self.callback({
                            "type": "tool_result",
                            "tool": func_name,
                            "result": result
                        })

                    # Add tool result to conversation
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str)
                    })

                # Continue loop — LLM will process tool results
                continue

            # Case 2: LLM returned a final text response (no tool calls)
            else:
                final_text = message.content or "I'm not sure how to respond to that."

                # Inject pre-formatted mention results JSON if a mention tool just ran.
                pending_json = self.session_data.pop('pending_display_json', None)
                if pending_json:
                    logger.info(f"INJECTING display_json into response ({len(pending_json)} chars)")
                    final_text = pending_json + "\n\nWould you like me to create video clips for any of these mentions?"

                # Inject visual findings if the LLM ignored them
                pending_visual = self.session_data.pop('pending_visual_answer', None)
                if pending_visual and not pending_json:
                    # Check if the LLM already included visual info
                    has_visual_in_response = any(kw in final_text.lower() for kw in ['green', 'sleeveless', 'anchor', 'wearing', 'visual'])
                    if not has_visual_in_response:
                        logger.info("LLM ignored visual results — injecting visual findings")
                        final_text = final_text.rstrip() + "\n\n**Visual observations from the video:**\n" + pending_visual

                self.messages.append({"role": "assistant", "content": final_text})

                if self.callback:
                    self.callback({"type": "answer", "content": final_text})

                return final_text

        # Safety: hit max iterations
        timeout_msg = "I've reached the maximum number of steps for this request. Please try breaking your request into smaller parts."
        self.messages.append({"role": "assistant", "content": timeout_msg})
        
        if self.callback:
            self.callback({"type": "answer", "content": timeout_msg})
            
        return timeout_msg

    def _execute_tool(self, tool_name: str, args: Dict) -> Dict:
        """
        Execute a tool by name with the given arguments.

        Args:
            tool_name: Name of the tool to execute
            args: Arguments for the tool

        Returns:
            Dict with the tool result
        """
        try:
            if tool_name == "check_video_exists":
                return self._tool_check_video_exists(args)
            elif tool_name == "download_youtube_video":
                return self._tool_download_youtube(args)
            elif tool_name == "extract_audio":
                return self._tool_extract_audio(args)
            elif tool_name == "transcribe_audio":
                return self._tool_transcribe_audio(args)
            elif tool_name == "generate_and_store_embeddings":
                return self._tool_generate_embeddings(args)
            elif tool_name == "search_video_context":
                return self._tool_search_context(args)
            elif tool_name == "list_processed_videos":
                return self._tool_list_videos(args)
            elif tool_name == "trim_video":
                return self._tool_trim_video(args)
            elif tool_name == "create_highlight_clip":
                return self._tool_create_highlights(args)
            elif tool_name == "count_mentions_in_video":
                return self._tool_count_mentions_in_video(args)
            elif tool_name == "index_video_visuals":
                return self._tool_index_video_visuals(args)
            elif tool_name == "search_image_context_from_video":
                return self._tool_search_image_context(args)
            elif tool_name == "create_clips_from_mentions":
                return self._tool_create_clips_from_mentions(args)
            elif tool_name == "generate_viral_short":
                return self._tool_generate_viral_short(args)
            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}")
            return {"error": str(e), "tool": tool_name}

    # ============= TOOL IMPLEMENTATIONS =============

    def _tool_check_video_exists(self, args: Dict) -> Dict:
        """Check if video embeddings/transcripts exist in ChromaDB AND on disk.
        A video is only 'Ready' if BOTH ChromaDB embeddings AND files exist."""
        video_id = args.get("video_id", "")

        # Standardize ID
        if not video_id.startswith('youtube_') and len(video_id) == 11:
            video_id = f"youtube_{video_id}"

        result = self.chroma_store.check_video_exists(video_id)

        # Try to find title in session if missing
        title = self.session_data.get('last_metadata', {}).get('title', 'Unknown')

        # Check files on disk too
        has_transcript = os.path.exists(f"./storage/transcripts/{video_id}_transcript.json")
        has_video = False
        potential_dir = Path("./storage/videos") / video_id
        if potential_dir.exists():
            for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
                v_file = potential_dir / f"video{ext}" if ext else potential_dir / "video"
                if v_file.exists():
                    has_video = True
                    break

        # Also check if video is soft-deleted in SQLite
        is_deleted = False
        try:
            video_record = self.sqlite_store.get_video(video_id)
            if video_record and video_record.get('is_deleted'):
                is_deleted = True
            if video_record:
                title = video_record.get('title', title)
        except Exception:
            pass

        # A video is truly "exists" only if:
        # 1. ChromaDB has embeddings AND
        # 2. Transcript file exists on disk AND
        # 3. Video is NOT soft-deleted
        truly_exists = result['exists'] and has_transcript and not is_deleted

        if truly_exists:
            # Set as current video context
            self.session_data['last_video_id'] = video_id

            # Restore last_video_path
            if has_video and potential_dir.exists():
                for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
                    v_file = potential_dir / f"video{ext}" if ext else potential_dir / "video"
                    if v_file.exists():
                        self.session_data['last_video_path'] = str(v_file.resolve())
                        break
        elif result['exists'] and (not has_transcript or is_deleted):
            # ChromaDB has stale embeddings but files are gone or video is deleted
            # Clean up ChromaDB to prevent future false positives
            logger.warning(f"Stale ChromaDB data for {video_id} (transcript={has_transcript}, deleted={is_deleted}). Cleaning up.")
            self._cleanup_stale_embeddings(video_id)

        return {
            "exists": truly_exists,
            "embedded": truly_exists,  # Only "embedded" if fully verified (not stale)
            "transcribed": has_transcript,
            "downloaded": has_video,
            "is_deleted": is_deleted,
            "video_id": video_id,
            "title": title,
            "chunk_count": result.get('count', 0) if truly_exists else 0,
            "status": "Ready" if truly_exists else ("Deleted" if is_deleted else "Not found")
        }

    def _cleanup_stale_embeddings(self, video_id: str):
        """Remove stale embeddings from ALL ChromaDB collections for a deleted/missing video."""
        from models.chroma_store import VIDEO_TRANSCRIPTS_V2, VIDEO_VISUAL_EMBEDDINGS
        for collection_name in ['video_transcripts', VIDEO_TRANSCRIPTS_V2, VIDEO_VISUAL_EMBEDDINGS]:
            try:
                collection = self.chroma_store.client.get_collection(name=collection_name)
                # Get all IDs for this video
                results = collection.get(where={"video_id": {"$eq": video_id}})
                if results['ids']:
                    collection.delete(ids=results['ids'])
                    logger.info(f"Cleaned {len(results['ids'])} stale embeddings from '{collection_name}' for {video_id}")
            except Exception as e:
                logger.debug(f"Could not clean {collection_name} for {video_id}: {e}")

    def _tool_download_youtube(self, args: Dict) -> Dict:
        """Download a YouTube video (with internal existence check)"""
        youtube_url = args.get("youtube_url", "")

        # Extract YouTube ID
        youtube_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', youtube_url)
        youtube_id = youtube_id_match.group(1) if youtube_id_match else ""
        video_id = f"youtube_{youtube_id}" if youtube_id else ""

        # Internal check: if fully processed (embeddings + files + not deleted), skip
        if video_id:
            check = self._tool_check_video_exists({"video_id": video_id})
            if check['exists']:  # 'exists' = verified (ChromaDB + files + not deleted)
                logger.info(f"Video {video_id} already fully processed. Skipping download/transcription pipeline.")
                # Set as current context
                self.session_data['last_video_id'] = video_id
                self.session_data['last_metadata'] = {'title': check.get('title', 'Unknown')}
                return {
                    "status": "already_exists",
                    "video_id": video_id,
                    "title": check.get('title', 'Unknown'),
                    "chunks": check.get('chunk_count', 0),
                    "embedded": True,
                    "message": f"✓ Video ALREADY FULLY PROCESSED: '{check.get('title', 'Unknown')}' ({video_id}) with {check.get('chunk_count', 0)} embedded chunks. SKIP download, transcription, and embedding steps. You can immediately search the context or answer questions."
                }

        # Perform download
        video_path, metadata = self.video_processor.download_youtube(youtube_url)
        
        # Fallback for video_id if extraction failed earlier
        if not video_id:
            youtube_id = Path(video_path).parent.name.replace('youtube_', '')
            video_id = f"youtube_{youtube_id}"

        # Store in session (including youtube_url for later use in metadata)
        self.session_data['last_video_path'] = video_path
        self.session_data['last_metadata'] = metadata
        self.session_data['last_metadata']['youtube_url'] = youtube_url  # Store the URL
        self.session_data['last_video_id'] = video_id

        return {
            "status": "success",
            "video_path": video_path,
            "video_id": video_id,
            "metadata": metadata,
            "message": f"Video downloaded: {metadata.get('title', 'Unknown')}. Next: extract_audio then transcribe."
        }

    def _tool_extract_audio(self, args: Dict) -> Dict:
        """Extract audio from video"""
        video_path = args.get("video_path", "")
        audio_path = self.video_processor.extract_audio(video_path)

        self.session_data['last_audio_path'] = audio_path

        return {
            "status": "success",
            "audio_path": audio_path,
            "message": f"Audio extracted to: {audio_path}"
        }

    def _tool_transcribe_audio(self, args: Dict) -> Dict:
        """Transcribe audio to text"""
        audio_path = args.get("audio_path", "")
        language = args.get("language", "auto")

        transcript_data = self.transcriber.transcribe_audio(
            audio_path=audio_path,
            language=language
        )

        # Save transcript to disk
        video_id = self.session_data.get('last_video_id', Path(audio_path).stem)
        transcript_file = f"./storage/transcripts/{video_id}_transcript.json"
        os.makedirs("./storage/transcripts", exist_ok=True)
        self.transcriber.save_transcript(transcript_data, transcript_file)

        self.session_data['last_transcript'] = transcript_data
        self.session_data['last_transcript_file'] = transcript_file

        return {
            "status": "success",
            "video_id": video_id,
            "total_segments": len(transcript_data.get('segments', [])),
            "duration": transcript_data.get('duration', 0),
            "language": transcript_data.get('language', language),
            "transcript_file": transcript_file,
            "message": f"Transcribed {len(transcript_data.get('segments', []))} segments. Transcript saved and ready for embedding generation."
        }

    def _tool_generate_embeddings(self, args: Dict) -> Dict:
        """Generate embeddings and store in ChromaDB"""
        video_id = args.get("video_id", "")

        # Always use session data for transcript (LLM can't pass complex objects reliably)
        transcript_data = self.session_data.get('last_transcript')

        # Fallback: try loading from disk
        if not transcript_data:
            transcript_file = f"./storage/transcripts/{video_id}_transcript.json"
            if os.path.exists(transcript_file):
                with open(transcript_file, 'r', encoding='utf-8') as f:
                    transcript_data = json.load(f)
                logger.info(f"Loaded transcript from disk: {transcript_file}")

        if not transcript_data:
            return {"error": "No transcript data available. Run transcribe_audio first."}

        # Process for RAG (chunking + embeddings)
        rag_data = self.rag_processor.process_transcript_for_rag(transcript_data)

        # Get metadata from session
        metadata = self.session_data.get('last_metadata', {})
        title = metadata.get('title', video_id)
        channel = metadata.get('channel', '')
        youtube_url = metadata.get('youtube_url', '')

        # Store in ChromaDB with full metadata
        num_stored = self.chroma_store.add_embeddings(
            collection_name='video_transcripts',
            video_id=video_id,
            chunks=rag_data['chunks'],
            title=title,
            channel=channel,
            youtube_url=youtube_url
        )

        # Sync to SQLite Database so it appears in the VideosPage UI
        try:
            from datetime import datetime
            self.sqlite_store.upsert_video({
                'id': video_id,
                'title': title,
                'channel': channel,
                'url': youtube_url,
                'published_at': metadata.get('upload_date', ''),
                'processed_at': metadata.get('transcribed_at', datetime.now().isoformat()),
                'transcript_path': self.session_data.get('last_transcript_file', ''),
                'audio_path': self.session_data.get('last_audio_path', ''),
                'video_path': self.session_data.get('last_video_path', '')
            })
            logger.info(f"Video {video_id} synchronized to SQLite database.")
        except Exception as e:
            logger.error(f"Failed to sync video {video_id} to SQLite: {e}")

        # Save RAG data to file
        rag_file = f"./storage/rag/{video_id}_rag.json"
        os.makedirs("./storage/rag", exist_ok=True)
        with open(rag_file, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, indent=2, default=str)

        # Also generate v2 embeddings (Qwen3 via OpenRouter) for semantic search
        v2_count = 0
        try:
            if self.openrouter_embedder:
                v2_count = self.rag_processor.reembed_transcript_for_v2(
                    video_id=video_id,
                    openrouter_embedder=self.openrouter_embedder,
                    chroma_store=self.chroma_store,
                    title=title,
                    channel=channel,
                    youtube_url=youtube_url
                )
                logger.info(f"V2 embeddings generated: {v2_count} dense chunks for {video_id}")
        except Exception as e:
            logger.warning(f"V2 embedding generation failed (non-critical): {e}")

        # Also generate visual embeddings (keyframes → NVIDIA Nemotron VL)
        visual_count = 0
        try:
            if self.openrouter_embedder:
                visual_result = self._tool_index_video_visuals({"video_id": video_id})
                if visual_result.get('status') == 'success':
                    visual_count = visual_result.get('frames_indexed', 0)
                    logger.info(f"Visual embeddings generated: {visual_count} frames for {video_id}")
        except Exception as e:
            logger.warning(f"Visual embedding generation failed (non-critical): {e}")

        return {
            "status": "success",
            "video_id": video_id,
            "total_chunks": len(rag_data['chunks']),
            "embeddings_stored": num_stored,
            "v2_chunks": v2_count,
            "rag_file": rag_file,
            "message": f"Generated and stored {len(rag_data['chunks'])} v1 + {v2_count} v2 embeddings for video '{video_id}'"
        }

    def _search_with_fallback(self, query_embedding, vid_id: str, top_k: int) -> list:
        """Search ChromaDB with automatic prefix fallback (handles youtube_ prefix mismatch)"""
        results = self.chroma_store.search(
            collection_name='video_transcripts',
            query_embedding=query_embedding,
            video_id=vid_id,
            top_k=top_k
        )
        # If no results, try alternate prefix format
        if not results:
            if vid_id.startswith('youtube_'):
                alt_id = vid_id[len('youtube_'):]  # Strip prefix
            else:
                alt_id = f'youtube_{vid_id}'       # Add prefix
            results = self.chroma_store.search(
                collection_name='video_transcripts',
                query_embedding=query_embedding,
                video_id=alt_id,
                top_k=top_k
            )
        return results

    def _tool_search_context(self, args: Dict) -> Dict:
        """Search ChromaDB for relevant video context (supports single or multiple videos)"""
        video_id = args.get("video_id", "")
        query = args.get("query", "")
        top_k = args.get("top_k", 5)

        # Generate query embedding
        query_embedding = self.rag_processor.generate_embedding(query)

        # Check if we have reference videos in session (multi-video mode)
        reference_video_ids = self.session_data.get('reference_video_ids', [])

        if reference_video_ids and len(reference_video_ids) > 0:
            # Multi-video search: search across all reference videos
            all_results = []
            for vid_id in reference_video_ids:
                results = self._search_with_fallback(query_embedding, vid_id, top_k)
                all_results.extend(results)

            # Sort by similarity and take top_k
            all_results = sorted(all_results, key=lambda x: x.get('similarity', 0), reverse=True)[:top_k]
            results = all_results
            video_ids_str = ', '.join(reference_video_ids)
        else:
            # Single video search (backward compatibility)
            results = self._search_with_fallback(query_embedding, video_id, top_k)
            video_ids_str = video_id

        # Format results for LLM
        formatted = []
        for r in results:
            metadata = r.get('metadata', {})
            start = float(metadata.get('start_time', 0))
            end = float(metadata.get('end_time', 0))
            video_title = metadata.get('title', 'Unknown')
            formatted.append({
                "text": r.get('text', ''),
                "start_time": start,
                "end_time": end,
                "timestamp": f"{self._fmt_time(start)} - {self._fmt_time(end)}",
                "speakers": metadata.get('speakers', ''),
                "similarity": r.get('similarity', 0),
                "video_title": video_title
            })

        return {
            "status": "success",
            "video_id": video_ids_str,
            "query": query,
            "results_count": len(formatted),
            "results": formatted,
            "instruction": "These are TRANSCRIPT excerpts of what was SAID in the video. Use these to answer the user's question. Combine with visual search results if available."
        }

    def _tool_list_videos(self, args: Dict) -> Dict:
        """List all unique videos processed in ChromaDB"""
        try:
            videos = self.chroma_store.get_all_videos('video_transcripts')
            
            # If nothing found, check directory structure as fallback
            if not videos:
                storage_videos = []
                video_dir = Path("./storage/videos")
                if video_dir.exists():
                    for d in video_dir.iterdir():
                        if d.is_dir() and d.name.startswith('youtube_'):
                            storage_videos.append({"video_id": d.name, "title": "Processed (No Title Found)"})
                videos = storage_videos

            return {
                "status": "success",
                "total_videos": len(videos),
                "videos": videos,
                "note": "Mention these titles or IDs to the user."
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _tool_trim_video(self, args: Dict) -> Dict:
        """Trim a video to a specific time range"""
        video_path = args.get("video_path", self.session_data.get('last_video_path', ''))
        start = args.get("start_seconds", 0)
        end = args.get("end_seconds", 0)
        output_name = args.get("output_name", None)

        output_path = self.video_tools.trim_video(
            video_path=video_path,
            start_seconds=start,
            end_seconds=end,
            output_name=output_name
        )

        return {
            "status": "success",
            "output_path": output_path,
            "start": start,
            "end": end,
            "message": f"Video trimmed: {self._fmt_time(start)} to {self._fmt_time(end)} → {output_path}"
        }

    def _tool_create_highlights(self, args: Dict) -> Dict:
        """Create a highlight reel from multiple segments"""
        video_path = args.get("video_path", self.session_data.get('last_video_path', ''))
        segments = args.get("segments", [])
        output_name = args.get("output_name", None)

        output_path = self.video_tools.create_highlight_clip(
            video_path=video_path,
            segments=segments,
            output_name=output_name
        )

        return {
            "status": "success",
            "output_path": output_path,
            "segments_count": len(segments),
            "message": f"Highlight clip created with {len(segments)} segments → {output_path}"
        }

    def _format_mention_results_json(self, result: Dict) -> Dict:
        """
        Pre-format the mention results as the EXACT JSON block the frontend expects.
        ALWAYS produces display_json — even for 0 mentions (shows empty card).
        """
        if result.get('status') == 'error':
            return result

        mentions = result.get('mentions', [])
        statistics = result.get('statistics', {})

        # Get video title from first mention or session or SQLite
        video_title = "Unknown"
        if mentions:
            video_title = mentions[0].get('title', 'Unknown')
        if video_title == "Unknown":
            video_title = self.session_data.get('last_metadata', {}).get('title', 'Unknown')
        if video_title == "Unknown":
            # Try SQLite
            try:
                vid = result.get('video_id', '')
                if vid:
                    record = self.sqlite_store.get_video(vid)
                    if record:
                        video_title = record.get('title', 'Unknown')
            except Exception:
                pass

        # Calculate average confidence
        confidences = [m.get('confidence', 0) for m in mentions]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Build the formatted mention list (max 15)
        formatted_mentions = []
        for m in mentions[:15]:
            ts = m.get('timestamp_formatted', '0:00')
            # Extract just the start time (before the " - ")
            start_ts = ts.split(' - ')[0] if ' - ' in ts else ts
            formatted_mentions.append({
                "timestamp": start_ts,
                "text": m.get('text', '')[:200],
                "confidence": round(m.get('confidence', 0), 2)
            })

        # Build the JSON block
        json_block = {
            "type": "mention_results",
            "data": {
                "search_query": result.get('query', ''),
                "video_title": video_title,
                "total_mentions": result.get('total_count', 0),
                "average_confidence": round(avg_confidence, 2),
                "time_distribution": statistics.get('time_distribution', {}),
                "mentions": formatted_mentions
            }
        }

        # Add pre-formatted JSON string to result
        result['display_json'] = "```json\n" + json.dumps(json_block, indent=2) + "\n```"
        result['instruction'] = "OUTPUT ONLY the display_json field below AS-IS. Do NOT add any text before or after it."
        return result

    def _validate_videos_ready(self, video_ids: List[str]) -> Dict:
        """
        Check that all requested videos are actually processed and ready.
        Returns error dict if any video is missing, or None if all are ready.
        """
        missing = []
        for vid in video_ids:
            check = self._tool_check_video_exists({"video_id": vid})
            if not check.get('exists'):
                missing.append(vid)

        if missing:
            return {
                "status": "error",
                "message": f"Video(s) not ready: {', '.join(missing)}. "
                           f"Please provide the YouTube URL so I can download and process the video first. "
                           f"Use download_youtube_video, then extract_audio, transcribe_audio, and generate_and_store_embeddings."
            }
        return None  # All good

    def _tool_count_mentions_in_video(self, args: Dict) -> Dict:
        """
        HYBRID mention search — always runs BOTH regex + semantic, merges results.
        Single tool for all mention queries.
        """
        try:
            from modules.mention_counter import MentionCounter

            video_ids = args.get("video_ids", [])
            search_query = args.get("search_query", "")

            if not video_ids or not search_query:
                return {
                    "status": "error",
                    "message": "video_ids and search_query are required"
                }

            # Validate all videos are actually processed and ready
            validation_error = self._validate_videos_ready(video_ids)
            if validation_error:
                return validation_error

            logger.info(f"HYBRID mention search for '{search_query}' in {len(video_ids)} video(s)")

            counter = MentionCounter(self.chroma_store, self.rag_processor, self.openrouter_embedder)

            # Always hybrid — runs both regex AND semantic, merges results
            result = counter.count_mentions(
                video_ids=video_ids,
                search_query=search_query,
                mode='hybrid',
                confidence_threshold=0.3
            )

            result = self._format_mention_results_json(result)
            if result.get('display_json'):
                self.session_data['pending_display_json'] = result['display_json']
            return result

        except Exception as e:
            logger.error(f"Error in hybrid mention search: {str(e)}")
            return {
                "status": "error",
                "message": f"Hybrid mention search failed: {str(e)}"
            }

    def _tool_index_video_visuals(self, args: Dict) -> Dict:
        """Extract keyframes from video and generate visual embeddings."""
        try:
            from modules.video_chunker import VideoChunker

            video_id = args.get("video_id", "")
            if not video_id:
                return {"status": "error", "message": "video_id is required"}

            # Check if already indexed
            if self.chroma_store.check_visual_index_exists(video_id):
                logger.info(f"Video {video_id} already has visual embeddings, skipping")
                return {
                    "status": "already_indexed",
                    "video_id": video_id,
                    "message": f"Visual embeddings already exist for {video_id}"
                }

            if not self.openrouter_embedder:
                return {"status": "error", "message": "OpenRouterEmbedder not available"}

            # Resolve video path
            video_path = self.session_data.get('last_video_path', '')
            metadata = self.session_data.get('last_metadata', {})
            title = metadata.get('title', 'Unknown')
            channel = metadata.get('channel', '')
            youtube_url = metadata.get('youtube_url', '')

            if self.callback:
                self.callback({"type": "status", "content": "Extracting keyframes from video..."})

            # Extract keyframes
            chunker = VideoChunker(chunk_duration=30)
            frames = chunker.extract_keyframes(video_path, video_id)

            if not frames:
                return {"status": "error", "message": f"No keyframes extracted from {video_id}"}

            logger.info(f"Extracted {len(frames)} keyframes for {video_id}")

            if self.callback:
                self.callback({"type": "status", "content": f"Describing {len(frames)} keyframes with Seed 2.0 Vision..."})

            # Step 1: Describe each keyframe with vision LLM (for RAG context)
            frame_paths = [f['frame_path'] for f in frames]
            descriptions = self.openrouter_embedder.describe_image_batch(frame_paths, rate_limit_delay=1.0)

            # Attach descriptions to frames
            for frame, desc in zip(frames, descriptions):
                frame['description'] = desc

            if self.callback:
                self.callback({"type": "status", "content": f"Embedding {len(frames)} keyframes with NVIDIA Nemotron VL..."})

            # Step 2: Embed all keyframes with NVIDIA (for vector search)
            embeddings = self.openrouter_embedder.embed_image_batch(frame_paths, rate_limit_delay=3.0)

            # Attach embeddings to frames (skip zero/failed embeddings)
            embedded_frames = []
            for frame, embedding in zip(frames, embeddings):
                if any(v != 0.0 for v in embedding[:10]):  # Not a zero vector
                    frame['embedding'] = embedding
                    embedded_frames.append(frame)

            if not embedded_frames:
                chunker.cleanup(video_id)
                return {"status": "error", "message": "All frame embeddings failed"}

            # Store in ChromaDB
            count = self.chroma_store.add_visual_embeddings(
                video_id=video_id,
                frames=embedded_frames,
                title=title,
                channel=channel,
                youtube_url=youtube_url
            )

            # Cleanup temp frame files
            chunker.cleanup(video_id)

            logger.info(f"Visual indexing complete: {count} frames for {video_id}")

            return {
                "status": "success",
                "video_id": video_id,
                "frames_extracted": len(frames),
                "frames_indexed": count,
                "message": f"Indexed {count} visual keyframes for {video_id}"
            }

        except Exception as e:
            logger.error(f"Visual indexing failed for {args.get('video_id', '?')}: {e}")
            return {"status": "error", "message": f"Visual indexing failed: {str(e)}"}

    def _tool_search_image_context(self, args: Dict) -> Dict:
        """Search visual embeddings for matching scenes/frames."""
        try:
            video_ids = args.get("video_ids", [])
            query = args.get("query", "")
            top_k = args.get("top_k", 5)

            if not query:
                return {"status": "error", "message": "query is required"}

            # Use reference videos from session if not provided
            if not video_ids:
                video_ids = self.session_data.get('reference_video_ids', [])
            if not video_ids:
                return {"status": "error", "message": "No video_ids provided and no reference videos selected"}

            if not self.openrouter_embedder:
                return {"status": "error", "message": "OpenRouterEmbedder not available for visual search"}

            logger.info(f"Visual search for '{query}' in {len(video_ids)} video(s)")

            # Embed query with NVIDIA model (same vector space as images)
            query_embedding = self.openrouter_embedder.embed_visual_query(query)

            # Search visual collection
            results = self.chroma_store.search_visual(
                query_embedding=query_embedding,
                video_ids=video_ids,
                threshold=0.15,  # Lower threshold for cross-modal (image↔text) search
                top_k=top_k
            )

            # Format results (same pattern as _tool_search_context)
            formatted = []
            for r in results:
                metadata = r.get('metadata', {})
                start_time = float(metadata.get('start_time', 0))
                end_time = float(metadata.get('end_time', 0))
                formatted.append({
                    "text": r.get('text', ''),  # AI-generated frame description
                    "start_time": start_time,
                    "end_time": end_time,
                    "timestamp": f"{self._fmt_time(start_time)} - {self._fmt_time(end_time)}",
                    "similarity": round(r.get('similarity', 0), 4),
                    "video_id": metadata.get('video_id', ''),
                    "video_title": metadata.get('title', 'Unknown'),
                    "source_type": "visual"
                })

            # Build a clear answer summary the LLM can relay directly
            answer_lines = []
            for r in formatted:
                answer_lines.append(f"- At {r['timestamp']}: {r.get('text', 'N/A')}")
            answer_summary = "\n".join(answer_lines) if answer_lines else "No visual matches found."

            return {
                "status": "success",
                "source": "visual",
                "query": query,
                "results_count": len(formatted),
                "results": formatted,
                "answer_summary": f"VISUAL FINDINGS (what was SEEN in the video):\n{answer_summary}",
                "instruction": "IMPORTANT: The answer_summary above contains REAL visual observations from the video. You MUST include these findings in your response. Do NOT say 'no visual results' — the results ARE above."
            }

        except Exception as e:
            logger.error(f"Visual search failed: {e}")
            return {"status": "error", "message": f"Visual search failed: {str(e)}"}

    def _tool_create_clips_from_mentions(self, args: Dict) -> Dict:
        """Create video clips from mention timestamps"""
        try:
            from modules.clip_generator import ClipGenerator

            video_id = args.get("video_id", "")
            mentions = args.get("mentions", [])
            clip_duration_before = args.get("clip_duration_before", 2.0)
            clip_duration_after = args.get("clip_duration_after", 3.0)
            smart_grouping = args.get("smart_grouping", False)
            grouping_threshold_seconds = args.get("grouping_threshold_seconds", 7.0)
            expansion_mode = args.get("expansion_mode", "default")

            if not video_id or not mentions:
                return {
                    "status": "error",
                    "message": "video_id and mentions are required"
                }

            logger.info(f"Creating clips from {len(mentions)} mentions in {video_id} (expansion: {expansion_mode})")

            # Get video path from session or disk
            video_path = self.session_data.get('last_video_path', '')

            # If not in session, try to find on disk
            if not video_path or not os.path.exists(video_path):
                potential_dirs = [
                    Path("./storage/videos") / video_id,
                    Path("./storage/videos") / video_id.replace('youtube_', '')
                ]

                for potential_dir in potential_dirs:
                    if potential_dir.exists():
                        for ext in ['.mp4', '.mkv', '.avi', '.webm', '']:
                            v_file = potential_dir / f"video{ext}" if ext else potential_dir / "video"
                            if v_file.exists():
                                video_path = str(v_file.resolve())
                                break
                    if video_path:
                        break

            if not video_path or not os.path.exists(video_path):
                logger.error(f"Video file not found for {video_id}")
                return {
                    "status": "error",
                    "message": f"Could not find video file for {video_id}"
                }

            # Create clips
            clip_generator = ClipGenerator(storage_dir="./storage")
            result = clip_generator.create_clips_from_mentions(
                video_id=video_id,
                video_path=video_path,
                mentions=mentions,
                clip_duration_before=clip_duration_before,
                clip_duration_after=clip_duration_after,
                smart_grouping=smart_grouping,
                grouping_threshold_seconds=grouping_threshold_seconds,
                expansion_mode=expansion_mode
            )

            logger.info(f"Clip creation result: {result.get('status')}")
            return result

        except Exception as e:
            logger.error(f"Error creating clips: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to create clips: {str(e)}"
            }

    def _tool_generate_viral_short(self, args: Dict) -> Dict:
        """Automated pipeline to find topics, extract best segment, and generate a viral short"""
        video_id = args.get("video_id")
        topic = args.get("topic")

        if not video_id or not topic:
            return {"status": "error", "message": "video_id and topic are required"}

        logger.info(f"Generating viral short for '{topic}' in {video_id}")
        
        # 1. Count mentions to find occurrences
        mentions_resp = self._tool_count_mentions_in_video({
            "video_ids": [video_id],
            "search_query": topic,
            "search_mode": "hybrid"
        })
        
        mentions = mentions_resp.get("mentions", [])
        if not mentions:
            return {"status": "error", "message": f"Could not find any mentions of '{topic}' in the video."}
            
        # 2. Pick the longest mention or highest confidence
        # For a viral short, we want the most confident match of the topic
        best_mention = max(mentions, key=lambda x: x.get('confidence', 0))
        
        # 3. Pass to AI Director Clip Generator
        logger.info("Passing best mention to AI Director...")
        clip_resp = self._tool_create_clips_from_mentions({
            "video_id": video_id,
            "mentions": [best_mention],
            "expansion_mode": "ai_director",
            "smart_grouping": False
        })
        
        if clip_resp.get("status") != "success":
            return clip_resp
            
        # 4. Generate Catchy Title using the LLM
        logger.info("Generating catchy titles...")
        title_prompt = f"The user just generated a short video clip about the topic '{topic}'. Generate 3 highly engaging, clickbait-style titles (without being misleading) for YouTube Shorts or Instagram Reels. Respond with ONLY the titles, one per line. Do NOT use numbers like '1.', '2.', just the raw title string."
        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-4o-mini",
                messages=[{"role": "user", "content": title_prompt}],
                temperature=0.8,
                extra_headers={"HTTP-Referer": "http://localhost:5000", "X-OpenRouter-Title": "Video Chat Agent"}
            )
            titles = [t.strip().strip('"').strip("'") for t in response.choices[0].message.content.strip().split("\\n") if t.strip()]
        except Exception as e:
            logger.error(f"Failed to generate titles: {e}")
            titles = [f"{topic} - Viral Short", f"The truth about {topic}", f"What you didn't know about {topic}"]
            
        clip_resp["suggested_titles"] = titles
        return clip_resp

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS"""
        seconds = float(seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
