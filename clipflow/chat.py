"""Le o chat da Twitch de forma anonima (IRC, sem login)."""
import asyncio
import logging

log = logging.getLogger("chat")


async def run_chat(channel: str, on_message):
    while True:
        try:
            reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
            writer.write(b"NICK justinfan48213\r\n")
            writer.write(f"JOIN #{channel}\r\n".encode())
            await writer.drain()
            log.info("chat conectado: #%s", channel)
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="ignore").strip()
                if line.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                elif " PRIVMSG " in line:
                    try:
                        on_message(line.split(" PRIVMSG ", 1)[1].split(" :", 1)[1])
                    except IndexError:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as e:  # reconecta
            log.warning("chat caiu (%s); reconectando em 5 s", e)
        await asyncio.sleep(5)
