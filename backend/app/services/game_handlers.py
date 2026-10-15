from app.core.event_bus import Event, event_bus
from app.services.game_engine import game_engine_service
from app.ws.connection_manager import connection_manager
from app.ws.protocol import WSMessageEnvelope


async def handle_make_move(event: Event) -> None:
    if not event.user_id:
        return

    envelope = event.data.get("envelope", {})
    payload = envelope.get("payload", {})
    cell = payload.get("cell")
    msg_id = envelope.get("id")

    if cell is None:
        return

    result = await game_engine_service.make_move(event.user_id, cell)

    if "error" in result:
        error_env = WSMessageEnvelope(
            type="ERROR",
            ref=msg_id,
            payload={
                "code": result["error"],
                "message": result.get("message", "Jogada inválida."),
            },
        )
        await connection_manager.send_personal_message(event.user_id, error_env.model_dump_json())
        return

    match = result["match"]

    if result.get("game_over"):
        for uid in match.players:
            if result["reason"].value == "DRAW":
                res_type = "DRAW"
            elif uid == result["winner_id"]:
                res_type = "WIN"
            else:
                res_type = "LOSS"

            ended_env = WSMessageEnvelope(
                type="MATCH_ENDED",
                ref=msg_id,
                payload={
                    "match_id": match.match_id,
                    "result": res_type,
                    "reason": result["reason"].value,
                    "board": match.board,
                },
            )
            await connection_manager.send_personal_message(uid, ended_env.model_dump_json())
    else:
        state_env = WSMessageEnvelope(
            type="MATCH_STATE",
            ref=msg_id,
            payload={
                "match_id": match.match_id,
                "board": match.board,
                "turn": match.current_turn.value,
                "seq": 0,
                "last_move": {"cell": cell},
            },
        )
        for uid in match.players:
            await connection_manager.send_personal_message(uid, state_env.model_dump_json())


async def handle_game_user_disconnected(event: Event) -> None:
    """Caso o jogador caia no meio da partida, notifica o fim com DISCONNECT."""
    if not event.user_id:
        return

    res = await game_engine_service.handle_player_disconnect(event.user_id)
    if res:
        match = res["match"]
        for uid in match.players:
            res_type = "WIN" if uid == res["winner_id"] else "LOSS"
            ended_env = WSMessageEnvelope(
                type="MATCH_ENDED",
                payload={
                    "match_id": match.match_id,
                    "result": res_type,
                    "reason": "DISCONNECT",
                    "board": match.board,
                },
            )
            await connection_manager.send_personal_message(uid, ended_env.model_dump_json())


def setup_game_handlers() -> None:
    """Registra os ouvintes de jogo no EventBus."""
    event_bus.subscribe("cmd.move", handle_make_move)
    event_bus.subscribe("cmd.MOVE", handle_make_move)
    event_bus.subscribe("cmd.make_move", handle_make_move)
    event_bus.subscribe("cmd.MAKE_MOVE", handle_make_move)
    event_bus.subscribe("user.disconnected", handle_game_user_disconnected)
