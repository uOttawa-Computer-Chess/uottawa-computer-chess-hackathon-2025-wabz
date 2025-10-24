import os
import requests
import json
import time
import random
import chess
#import custom_move_picker # this is your engine

TOKEN = os.environ["lichess_token"]
H = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/x-ndjson",
}

# Smoke Test for
def smoke_test_token():
    global TOKEN
    H = {"Authorization": f"Bearer {TOKEN}"}
    me = requests.get("https://lichess.org/api/account", headers=H).json()
    print("Logged in as:", me["username"])


def ndjson_lines(resp):
    for line in resp.iter_lines(decode_unicode=True):
        if line:
            yield json.loads(line)


def accept_challenge(ch_id):
    r = requests.post(f"https://lichess.org/api/challenge/{ch_id}/accept", headers=H)
    print("Accept challenge", ch_id, r.status_code, r.text[:200])


def decline_challenge(ch_id, reason="generic"):
    r = requests.post(f"https://lichess.org/api/challenge/{ch_id}/decline",
                      headers=H, data={"reason": reason})
    print("Decline challenge", ch_id, r.status_code, r.text[:200])


def play_move(game_id, uci):
    r = requests.post(f"https://lichess.org/api/bot/game/{game_id}/move/{uci}", headers=H)
    print("Move", game_id, uci, r.status_code, r.text[:200])


def resign(game_id):
    requests.post(f"https://lichess.org/api/bot/game/{game_id}/resign", headers=H)


def challenge_user(username: str,
                   rated: bool = False,
                   clock_limit: int = 180,
                   clock_increment: int = 0,
                   color: str = "random",
                   variant: str = "standard"):
    url = f"https://lichess.org/api/challenge/{username}"
    data = {
        "rated": str(rated).lower(),
        "clock.limit": str(clock_limit),
        "clock.increment": str(clock_increment),
        "color": color,
        "variant": variant,
    }
    r = requests.post(url, headers=H, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def stream_game(game_id):
    """Stream a single game, maintain a board, and play random moves on our turns."""
    url = f"https://lichess.org/api/bot/game/stream/{game_id}"
    with requests.get(url, headers=H, stream=True, timeout=90) as resp:
        resp.raise_for_status()
        board = chess.Board()
        my_color = None  # True for white, False for black
        for msg in ndjson_lines(resp):
            t = msg.get("type")
            print("MSG TYPE:", t, "| RAW:",
                  msg if t != "gameState" else {"type": t, "ply": len(msg.get("moves", "").split())})

            if t == "gameFull":
                # Determine our color
                white_id = msg["white"]["id"]
                black_id = msg["black"]["id"]
                me = requests.get("https://lichess.org/api/account", headers={"Authorization": f"Bearer {TOKEN}"}).json()["id"]
                my_color = (white_id == me)
                # Apply existing moves
                for m in msg.get("state", {}).get("moves", "").split():
                    board.push(chess.Move.from_uci(m))
                our_turn = (board.turn is True and my_color) or (board.turn is False and my_color is False)
                if our_turn and not board.is_game_over():
                    move = custom_move_picker.pick_move(board)
                    play_move(game_id, move.uci())
            elif t == "gameState":
                # Sync new moves
                moves = msg.get("moves", "").split()
                # Rebuild board from scratch to be safe (small & robust)
                board = chess.Board()
                for m in moves:
                    board.push(chess.Move.from_uci(m))

                # Is it our turn?
                our_turn = (board.turn is True and my_color) or (board.turn is False and my_color is False)
                if our_turn and not board.is_game_over():
                    legal = list(board.legal_moves)
                    if not legal:
                        continue

                    move = random.choice(legal)  # random choice
                    # move = custom_move_picker.pick_move(board)
                    play_move(game_id, move.uci())
            elif t == "chatLine":
                # Optional: react to chat
                pass
            elif t == "opponentGone":
                # Opponent disconnected or flagged — do nothing
                pass

def main():
    # Stream account-level events forever
    url = "https://lichess.org/api/stream/event"
    while True:
        try:
            with requests.get(url, headers=H, stream=True, timeout=90) as resp:
                resp.raise_for_status()
                for event in ndjson_lines(resp):
                    etype = event.get("type")
                    if etype == "challenge":
                        ch = event["challenge"]
                        variant = ch["variant"]["key"]
                        # Example policy: only accept standard/bullet/blitz/rapid; decline correspondence/variants
                        acceptable = variant in {"standard"} and ch["speed"] in {"bullet", "blitz", "rapid"}
                        if acceptable:
                            accept_challenge(ch["id"])
                        else:
                            decline_challenge(ch["id"], reason="variant")
                    elif etype == "gameStart":
                        gid = event["game"]["id"]
                        print("Game start:", gid)
                        stream_game(gid)
                    elif etype == "gameFinish":
                        print("Game finished:", event["game"]["id"])
        except requests.exceptions.RequestException as e:
            print("Stream error, retrying in 3s:", e)
            time.sleep(3)


if __name__ == "__main__":
    # Quick capability check: bot mode must be enabled on the account you’re using
    me = requests.get("https://lichess.org/api/account", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    if not me.get("title") == "BOT":
        print("⚠Your account isn’t in BOT mode. Enable it at: https://lichess.org/account/oauth/bot")
    #challenge_user("OtherBotName", rated=False, clock_limit=180, clock_increment=2)
    main()
