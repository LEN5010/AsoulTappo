// The redeem dialog's line for each refusal of POST /api/redeem (protocol/PROTOCOL.md 兑换码). too_many_tries and
// login_required have their own states in the dialog; any other code shows the server's message.
const MESSAGES: Record<string, string> = {
  bad_code: "兑换码不存在",
  code_expired: "兑换码已过期",
  code_used_up: "兑换码已领完",
  already_redeemed: "已经兑换过了",
};

export function redeemMessage(code: string, message: string): string {
  return MESSAGES[code] ?? (message || "兑换失败");
}
