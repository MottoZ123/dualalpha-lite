import type { InviteAccess } from "./access-control";

export function cloudOwner(_request: Request, access: InviteAccess) {
  return { id: `invite:${access.subject}`, email: "", name: access.localPreview ? "本地预览用户" : "个人邀请码用户", localPreview: access.localPreview };
}
