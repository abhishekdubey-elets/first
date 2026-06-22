'use client';

import { useRef, useState, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import Link from 'next/link';
import { Sparkles, Send, Loader2, User, ExternalLink, Globe } from 'lucide-react';
import { askAssistant } from '@/lib/api';
import type { ChatAnswer, ChatSource, WebSource } from '@/lib/types';
import { PageHeader } from '@/components/PageHeader';
import { GlassCard } from '@/components/GlassCard';
import { cn } from '@/lib/utils';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  webSources?: WebSource[];
  fromWeb?: boolean;
}

const SUGGESTIONS = [
  'Who is the new Patna DM?',
  'List recent transfers in Tamil Nadu with their new postings',
  'Which officers were posted as District Collector?',
  'Summarise the latest IAS reshuffle',
];

function SourceChip({ s }: { s: ChatSource }) {
  const move = `${s.previous_posting || s.previous_district || '?'} → ${
    s.new_posting || s.new_district || '?'
  }`;
  const inner = (
    <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300 hover:border-brand-violet/40 hover:text-white">
      <span className="font-medium text-white">{s.officer_name}</span>
      <span className="truncate text-slate-400">· {move}</span>
      {s.source_url && <ExternalLink className="h-3 w-3 shrink-0 text-slate-500" />}
    </span>
  );
  return s.source_url ? (
    <a href={s.source_url} target="_blank" rel="noopener noreferrer">
      {inner}
    </a>
  ) : (
    <Link href={`/officers/${encodeURIComponent(s.officer_name)}`}>{inner}</Link>
  );
}

function WebChip({ s }: { s: WebSource }) {
  return (
    <a href={s.url} target="_blank" rel="noopener noreferrer">
      <span className="inline-flex max-w-full items-center gap-1 rounded-full border border-sky-400/20 bg-sky-400/10 px-2.5 py-1 text-xs text-sky-200 hover:border-sky-400/50 hover:text-white">
        <Globe className="h-3 w-3 shrink-0 text-sky-300" />
        <span className="truncate">{s.title}</span>
        {s.source && <span className="shrink-0 text-sky-300/70">· {s.source}</span>}
      </span>
    </a>
  );
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => askAssistant(q),
    onSuccess: (data: ChatAnswer) => {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          webSources: data.web_sources,
          fromWeb: data.from_web,
        },
      ]);
    },
    onError: () => {
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content:
            'Sorry — I couldn’t generate an answer (the local model may be busy). Please try again.',
        },
      ]);
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, ask.isPending]);

  const submit = (q: string) => {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setMessages((m) => [...m, { role: 'user', content: question }]);
    setInput('');
    ask.mutate(question);
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col space-y-4">
      <PageHeader
        title="Assistant"
        description="Ask questions about the tracked IAS transfers — answered from the records, with sources."
      />

      <GlassCard className="flex min-h-0 flex-1 flex-col p-0">
        {/* Conversation */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-gradient">
                <Sparkles className="h-6 w-6 text-white" />
              </div>
              <p className="mt-4 text-sm font-medium text-white">
                Ask about IAS transfers
              </p>
              <p className="mt-1 max-w-sm text-xs text-slate-400">
                Answers are grounded only in the records the system has collected.
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => submit(s)}
                    className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 hover:border-brand-violet/40 hover:text-white"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={cn('flex gap-3', m.role === 'user' && 'flex-row-reverse')}
            >
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                  m.role === 'user' ? 'bg-white/10' : 'bg-accent-gradient'
                )}
              >
                {m.role === 'user' ? (
                  <User className="h-4 w-4 text-slate-200" />
                ) : (
                  <Sparkles className="h-4 w-4 text-white" />
                )}
              </div>
              <div
                className={cn(
                  'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm',
                  m.role === 'user'
                    ? 'bg-brand-violet/20 text-white'
                    : 'bg-white/[0.04] text-slate-200'
                )}
              >
                {m.role === 'assistant' && m.fromWeb && (
                  <span className="mb-2 inline-flex items-center gap-1 rounded-full bg-sky-400/15 px-2 py-0.5 text-[10px] font-medium text-sky-200">
                    <Globe className="h-3 w-3" /> Live web search
                  </span>
                )}
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                {m.sources && m.sources.length > 0 && (
                  <div className="mt-3 border-t border-white/10 pt-2.5">
                    <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                      References ({m.sources.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {m.sources.map((s) => (
                        <SourceChip key={s.id} s={s} />
                      ))}
                    </div>
                  </div>
                )}
                {m.webSources && m.webSources.length > 0 && (
                  <div className="mt-3 border-t border-white/10 pt-2.5">
                    <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                      Web results ({m.webSources.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {m.webSources.map((s, i) => (
                        <WebChip key={i} s={s} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {ask.isPending && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-gradient">
                <Sparkles className="h-4 w-4 text-white" />
              </div>
              <div className="flex items-center gap-2 rounded-2xl bg-white/[0.04] px-4 py-2.5 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching the records and thinking…
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Input */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
          className="flex items-center gap-3 border-t border-white/10 px-4 py-3"
        >
          <input
            className="input-glass flex-1"
            placeholder="Ask about an officer, district, state, or reshuffle…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={ask.isPending}
          />
          <button
            type="submit"
            disabled={ask.isPending || !input.trim()}
            className="btn-gradient disabled:opacity-50"
          >
            {ask.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Ask
          </button>
        </form>
      </GlassCard>
    </div>
  );
}
