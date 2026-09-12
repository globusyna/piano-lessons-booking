import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export function CopyLinkButton({ token }: { token: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const url = `${window.location.origin}/s/${token}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* clipboard blocked */
    }
    setCopied(true);
    toast("Link copied");
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button
      type="button"
      onClick={copy}
      className="tnum inline-flex items-center gap-1.5 text-sm text-slate underline-offset-4 hover:text-foreground hover:underline"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      /s/{token}
    </button>
  );
}
