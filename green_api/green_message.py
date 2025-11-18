# green_api/green_message.py
from __future__ import annotations

from typing import Optional, List, Literal, Union
from pydantic import BaseModel, Field, ConfigDict

# -------------------------------------------------
# Interactive buttons (sent + response)
# -------------------------------------------------
class ButtonItem(BaseModel):
    buttonId: Optional[str] = None
    buttonText: str
    model_config = ConfigDict(extra="allow")

class ButtonsMessageData(BaseModel):
    typeMessage: Literal["buttonsMessage"]
    buttonsMessageData: dict
    bodyText: Optional[str] = None
    footerText: Optional[str] = None
    buttons: Optional[List[ButtonItem]] = None
    headerType: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class ButtonsResponseMessageData(BaseModel):
    typeMessage: Literal["buttonsResponseMessage"]
    buttonsResponseMessageData: dict   # {"selectedButtonId","selectedButtonText",...}
    selectedButtonId: Optional[str] = None
    selectedButtonText: Optional[str] = None
    model_config = ConfigDict(extra="allow")

# -------------------------------------------------
# Shared submodels
# -------------------------------------------------
class InstanceData(BaseModel):
    idInstance: int
    wid: Optional[str] = None
    typeInstance: Optional[Literal["whatsapp", "waba"]] = None
    model_config = ConfigDict(extra="allow")

class SenderData(BaseModel):
    chatId: Optional[str] = None          # "xxx@c.us" | "xxx@g.us"
    sender: Optional[str] = None          # jid of author (in groups)
    chatName: Optional[str] = None
    senderName: Optional[str] = None
    senderContactName: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class FilePayload(BaseModel):
    downloadUrl: str
    fileName: Optional[str] = None
    mimeType: Optional[str] = None
    caption: Optional[str] = None
    jpegThumbnail: Optional[str] = None
    size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    durationSeconds: Optional[int] = None
    ptt: Optional[bool] = None
    model_config = ConfigDict(extra="allow")

class QuotedMessage(BaseModel):
    stanzaId: Optional[str] = None
    participant: Optional[str] = None
    typeMessage: Optional[str] = None
    textMessage: Optional[str] = None
    fileMessageData: Optional[FilePayload] = None
    caption: Optional[str] = None
    jpegThumbnail: Optional[str] = None
    extendedTextMessage: Optional[dict] = None
    location: Optional[dict] = None
    contact: Optional[dict] = None
    model_config = ConfigDict(extra="allow")

# -------------------------------------------------
# messageData variants (discriminated by typeMessage)
# -------------------------------------------------
class TextMessageData(BaseModel):
    typeMessage: Literal["textMessage"]
    textMessageData: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class ExtendedTextMessageData(BaseModel):
    typeMessage: Literal["extendedTextMessage"]
    extendedTextMessageData: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class ReactionMessageData(BaseModel):
    typeMessage: Literal["reactionMessage"]
    reactionMessageData: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class StickerMessageData(BaseModel):
    typeMessage: Literal["stickerMessage"]
    stickerMessageData: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class FileMessageData(BaseModel):
    typeMessage: Literal["imageMessage", "videoMessage", "audioMessage", "documentMessage"]
    fileMessageData: FilePayload
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class LocationMessageData(BaseModel):
    typeMessage: Literal["locationMessage"]
    location: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

class ContactMessageData(BaseModel):
    typeMessage: Literal["contactMessage"]
    contact: dict
    quotedMessage: Optional[QuotedMessage] = None
    model_config = ConfigDict(extra="allow")

MessageData = Union[
    TextMessageData,
    ExtendedTextMessageData,
    ReactionMessageData,
    StickerMessageData,
    FileMessageData,
    LocationMessageData,
    ContactMessageData,
    ButtonsMessageData,
    ButtonsResponseMessageData,
]

# -------------------------------------------------
# Webhook event variants (discriminated by typeWebhook)
# -------------------------------------------------
class IncomingMessageReceived(BaseModel):
    typeWebhook: Literal["incomingMessageReceived"]
    instanceData: InstanceData
    timestamp: int
    idMessage: str
    senderData: SenderData
    messageData: MessageData = Field(discriminator="typeMessage")
    model_config = ConfigDict(extra="allow")

class OutgoingMessageReceived(BaseModel):
    typeWebhook: Literal["outgoingMessageReceived"]
    instanceData: InstanceData
    timestamp: int
    idMessage: str
    senderData: SenderData
    messageData: MessageData = Field(discriminator="typeMessage")
    model_config = ConfigDict(extra="allow")

class OutgoingAPIMessageReceived(BaseModel):
    typeWebhook: Literal["outgoingAPIMessageReceived"]
    instanceData: InstanceData
    timestamp: int
    idMessage: str
    senderData: SenderData
    messageData: MessageData = Field(discriminator="typeMessage")
    model_config = ConfigDict(extra="allow")

class OutgoingMessageStatus(BaseModel):
    typeWebhook: Literal["outgoingMessageStatus"]
    instanceData: InstanceData
    timestamp: int
    # nested or compact status payloads
    statusData: Optional[dict] = None
    status: Optional[str] = None
    chatId: Optional[str] = None
    messageId: Optional[str] = None
    sendByApi: Optional[bool] = None
    model_config = ConfigDict(extra="allow")

    def norm(self) -> dict:
        if self.statusData:
            sd = self.statusData
            return {
                "status": sd.get("status"),
                "chatId": sd.get("chatId"),
                "messageId": sd.get("messageId"),
                "sendByApi": sd.get("sendByApi"),
            }
        return {
            "status": self.status,
            "chatId": self.chatId,
            "messageId": self.messageId,
            "sendByApi": self.sendByApi,
        }

class StateInstanceChanged(BaseModel):
    typeWebhook: Literal["stateInstanceChanged"]
    instanceData: InstanceData
    timestamp: int
    stateInstance: str
    model_config = ConfigDict(extra="allow")

class StatusInstanceChanged(BaseModel):
    typeWebhook: Literal["statusInstanceChanged"]
    instanceData: InstanceData
    timestamp: int
    statusInstance: str
    model_config = ConfigDict(extra="allow")

# The union must be defined BEFORE WebhookEnvelope
WebhookEvent = Union[
    IncomingMessageReceived,
    OutgoingMessageReceived,
    OutgoingAPIMessageReceived,
    OutgoingMessageStatus,
    StateInstanceChanged,
    StatusInstanceChanged,
]

class WebhookEnvelope(BaseModel):
    event: WebhookEvent = Field(discriminator="typeWebhook")
    model_config = ConfigDict(extra="allow")

# Resolve forward references (important for discriminated unions)
WebhookEnvelope.model_rebuild()
