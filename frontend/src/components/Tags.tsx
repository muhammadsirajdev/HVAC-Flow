import type { Channel, Status } from "../api";
import { channelLabel, STATUS } from "../lib/format";
import { channelIcon, Icon } from "./Icon";

export function StatusTag({ status, size = "md" }: { status: Status; size?: "sm" | "md" }) {
  return (
    <span className={`status status--${status} status--${size}`} title={STATUS[status].hint}>
      <span className="status__dot" aria-hidden="true" />
      {STATUS[status].label}
    </span>
  );
}

export function ChannelTag({ channel, quiet = false }: { channel: Channel; quiet?: boolean }) {
  return (
    <span className={quiet ? "channel channel--quiet" : "channel"}>
      <Icon name={channelIcon(channel)} size={15} />
      {channelLabel(channel)}
    </span>
  );
}
