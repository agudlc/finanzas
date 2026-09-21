import { Badge } from '@/components/ui/badge';
import type { TranscriptBlock, TranscriptTurn } from '@/lib/types';

/**
 * The exchange with the model, as it happened.
 *
 * This is the only screen that shows the app's own English — the brief, the
 * tool calls and what they answered are what was sent, and rewriting them in
 * Spanish would make the one place meant for checking the run a place that
 * shows something else. It is read from top to bottom, so nothing is folded
 * away: a run that is worth opening is worth reading whole.
 */
export default function Transcript({ turns }: { turns: TranscriptTurn[] }) {
  return (
    <div className="flex flex-col gap-4">
      {turns.map((turn, index) => (
        <div key={index} className="flex flex-col gap-2">
          <span className="label">
            {turn.role === 'assistant' ? 'Claude' : 'Finanzas'}
          </span>
          {typeof turn.content === 'string' ? (
            <Said text={turn.content} />
          ) : (
            turn.content.map((block, at) => <Block key={at} block={block} />)
          )}
        </div>
      ))}
    </div>
  );
}

function Block({ block }: { block: TranscriptBlock }) {
  if (block.type === 'text') return <Said text={block.text} />;
  if (block.type === 'tool_use') {
    return (
      <div className="flex flex-col gap-1.5 rounded-lg bg-paper-2 p-3">
        <header className="leader">
          <span className="num text-xs">{block.name}</span>
          <Badge variant="outline">herramienta</Badge>
        </header>
        <Said text={JSON.stringify(block.input, null, 2)} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-paper-2 p-3">
      <header className="leader">
        <span className="label">respuesta</span>
        {block.is_error && <Badge variant="destructive">rechazada</Badge>}
      </header>
      <Said text={block.content} />
    </div>
  );
}

/** Text kept exactly as it was sent: the brief's own line breaks are its shape. */
function Said({ text }: { text: string }) {
  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-xs text-ink-mute">
      {text}
    </pre>
  );
}
