// Variation B — Brutalist / Anarchy Zine
// Raw edges, oversized type, caution yellow + bone white + black, rotated stamps,
// punk-zine photocopy energy that leans into the "anarchy" name.

const bColors = {
  bg:     '#f3efe4',   // bone / newsprint
  ink:    '#0b0b0b',
  paper:  '#faf6eb',
  yellow: '#ffd400',   // caution
  red:    '#e0301e',   // hazard red
  line:   '#0b0b0b',
  mute:   '#555048',
};

const bDisplay = "'Archivo Black', 'Archivo', ui-sans-serif, system-ui";
const bBody = "'Archivo', ui-sans-serif, system-ui";
const bMono = "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace";
const siteBase = '/canarchy';
const { useEffect, useState } = React;

function useViewport() {
  const getWidth = () => (typeof window === 'undefined' ? 1280 : window.innerWidth);
  const [width, setWidth] = useState(getWidth);

  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return {
    width,
    isMobile: width < 760,
    isTablet: width >= 760 && width < 1100,
  };
}

function sectionPadding(viewport, desktop = '70px 56px') {
  if (viewport.isMobile) return '42px 18px';
  if (viewport.isTablet) return '56px 28px';
  return desktop;
}

function CautionStripe({ h = 24, flip = false }) {
  return (
    <div style={{
      height: h,
      background: `repeating-linear-gradient(${flip ? '-45deg' : '45deg'}, ${bColors.yellow} 0 20px, ${bColors.ink} 20px 40px)`,
    }}/>
  );
}

const navLinks = [
  { label: 'DOCS',     href: siteBase + '/docs/getting_started' },
  { label: 'COMMANDS', href: siteBase + '/docs/command_spec' },
  { label: 'J1939',    href: siteBase + '/docs/tutorials/j1939_heavy_vehicle' },
  { label: 'AGENTS',   href: siteBase + '/docs/agents' },
  { label: 'GITHUB',   href: 'https://github.com/hexsecs/canarchy' },
];

function BrutNav({ viewport }) {
  const compact = viewport.isMobile;

  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'stretch', justifyContent: 'space-between',
        flexDirection: compact ? 'column' : 'row',
        background: bColors.ink, color: bColors.bg, borderBottom: `4px solid ${bColors.ink}`,
      }}>
        <div style={{ display: 'flex', alignItems: compact ? 'stretch' : 'center', gap: 0, flexDirection: compact ? 'column' : 'row' }}>
          <div style={{
            background: bColors.yellow, color: bColors.ink, padding: compact ? '16px 18px' : '18px 22px',
            fontFamily: bDisplay, fontSize: compact ? 20 : 22, letterSpacing: 1,
            borderRight: compact ? 'none' : `4px solid ${bColors.ink}`,
            borderBottom: compact ? `4px solid ${bColors.ink}` : 'none',
          }}>
            CAN/ARCHY
          </div>
          <div style={{ padding: compact ? '14px 18px' : '18px 22px', fontFamily: bMono, fontSize: compact ? 10 : 11, letterSpacing: 2, color: '#f3efe4' }}>
            STREAM-FIRST · AGENT-FIRST · J1939-FIRST
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
          {navLinks.map(link => (
            <a
              key={link.label}
              href={link.href}
              target={link.label === 'GITHUB' ? '_blank' : undefined}
              rel={link.label === 'GITHUB' ? 'noopener noreferrer' : undefined}
              style={{
                padding: compact ? '14px 16px' : '18px 20px',
                fontFamily: bBody, fontWeight: 800, fontSize: compact ? 12 : 13,
                letterSpacing: 2,
                borderLeft: compact ? 'none' : `2px solid ${bColors.bg}`,
                borderTop: compact ? `2px solid ${bColors.bg}` : 'none',
                cursor: 'pointer',
                background: link.label === 'GITHUB' ? bColors.red : 'transparent',
                color: bColors.bg,
                textDecoration: 'none', display: 'block',
                flex: compact ? '1 1 50%' : '0 0 auto',
                textAlign: compact ? 'center' : 'left',
              }}
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
      <CautionStripe h={14}/>
    </>
  );
}

function BrutHero({ viewport }) {
  const stacked = viewport.isMobile;

  return (
    <section style={{ padding: viewport.isMobile ? '42px 18px 26px' : viewport.isTablet ? '56px 28px 30px' : '60px 56px 30px', position: 'relative', overflow: 'hidden' }}>
      {/* Giant ID stamp */}
      <div style={{
        position: stacked ? 'static' : 'absolute', top: 80, right: -60, transform: stacked ? 'none' : 'rotate(9deg)',
        fontFamily: bMono, fontSize: 12, color: bColors.ink, border: `3px solid ${bColors.red}`,
        padding: '10px 18px', background: bColors.paper, letterSpacing: 2, fontWeight: 700,
        display: 'inline-block', marginBottom: stacked ? 18 : 0,
      }}>
        <div style={{ color: bColors.red }}>▲ ADVISORY</div>
        <div>FUZZ AROUND · FIND OUT</div>
      </div>

      {/* Date/issue tag */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: 30, fontFamily: bMono, fontSize: 11, flexWrap: 'wrap',
      }}>
        <span style={{ background: bColors.ink, color: bColors.yellow, padding: '4px 10px', letterSpacing: 2, fontWeight: 700 }}>ISSUE 04.1</span>
        <span style={{ background: bColors.yellow, color: bColors.ink, padding: '4px 10px', letterSpacing: 2, fontWeight: 700 }}>APR 2026</span>
        <span style={{ background: bColors.paper, color: bColors.ink, padding: '4px 10px', letterSpacing: 2, fontWeight: 700, border: `2px solid ${bColors.ink}` }}>FREE · TAKE ONE</span>
      </div>

      <h1 style={{
        fontFamily: bDisplay, fontSize: stacked ? 82 : viewport.isTablet ? 150 : 220, lineHeight: 0.82, letterSpacing: stacked ? -2 : -6,
        margin: 0, color: bColors.ink, textTransform: 'uppercase',
      }}>
        The bus<br/>
        <span style={{
          background: bColors.yellow, padding: stacked ? '0 8px' : '0 14px', marginLeft: stacked ? -8 : -14,
        }}>doesn't</span><br/>
        lie.
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: stacked ? '1fr' : viewport.isTablet ? '1fr' : '1.3fr 1fr', gap: stacked ? 24 : 56, marginTop: 50, alignItems: 'start' }}>
        <p style={{
          fontFamily: bBody, fontSize: stacked ? 18 : 22, lineHeight: 1.35, color: bColors.ink,
          margin: 0, fontWeight: 500, maxWidth: 640,
        }}>
          CANarchy is an <b>open, stream-first runtime</b> for analyzing and manipulating
          CAN and J1939 buses. Every command emits a canonical JSONL event. Every event is
          replayable. Nothing is hidden behind a GUI, a license key, or a dongle.
        </p>
        <div style={{ fontFamily: bMono, fontSize: 12, lineHeight: 1.8, color: bColors.ink, borderLeft: `4px solid ${bColors.ink}`, paddingLeft: 16 }}>
          <div style={{ color: bColors.red, fontWeight: 700, letterSpacing: 2, marginBottom: 8 }}>WHAT THIS IS</div>
          A toolkit for security researchers, red teams,<br/>
          fleet auditors, OSS tinkerers, and the<br/>
          occasional agent operating <i>without supervision.</i><br/>
          <br/>
          <div style={{ color: bColors.red, fontWeight: 700, letterSpacing: 2, marginBottom: 8 }}>WHAT IT IS NOT</div>
          A replacement for can-utils, python-can,<br/>
          SavvyCAN, or common sense.
        </div>
      </div>

      <div style={{ display: 'flex', gap: 0, marginTop: 50, flexWrap: 'wrap' }}>
        <a
          href="#"
          onClick={e => { e.preventDefault(); navigator.clipboard?.writeText('pip install canarchy'); }}
          style={{
            background: bColors.ink, color: bColors.yellow, padding: stacked ? '18px 22px' : '22px 30px',
            fontFamily: bDisplay, fontSize: stacked ? 18 : 20, letterSpacing: 1, textDecoration: 'none',
            border: `4px solid ${bColors.ink}`, textTransform: 'uppercase',
            width: stacked ? '100%' : 'auto',
          }}
        >
          pip install canarchy →
        </a>
        <a href={siteBase + '/docs/getting_started'} style={{
          background: bColors.yellow, color: bColors.ink, padding: stacked ? '18px 22px' : '22px 30px',
          fontFamily: bDisplay, fontSize: stacked ? 18 : 20, letterSpacing: 1, textDecoration: 'none',
          border: `4px solid ${bColors.ink}`, borderLeft: stacked ? `4px solid ${bColors.ink}` : 'none', borderTop: stacked ? 'none' : undefined, textTransform: 'uppercase',
          width: stacked ? '100%' : 'auto',
        }}>
          Read the Docs
        </a>
        <a href="https://github.com/hexsecs/canarchy" target="_blank" rel="noopener noreferrer" style={{
          background: bColors.paper, color: bColors.ink, padding: stacked ? '18px 22px' : '22px 30px',
          fontFamily: bDisplay, fontSize: stacked ? 18 : 20, letterSpacing: 1, textDecoration: 'none',
          border: `4px solid ${bColors.ink}`, borderLeft: stacked ? `4px solid ${bColors.ink}` : 'none', borderTop: stacked ? 'none' : undefined, textTransform: 'uppercase',
          width: stacked ? '100%' : 'auto',
        }}>
          ★ Star It
        </a>
      </div>
    </section>
  );
}

function BrutTicker() {
  const items = [
    'J1939 NATIVE', '·', 'JSONL WIRE FORMAT', '·', 'MCP SERVER', '·', 'UDS DISCOVERY',
    '·', 'DBC PROVIDERS', '·', 'REPLAY WITH JITTER', '·', 'FRAME GATEWAY', '·',
    'ACTIVE-COMMAND SAFETY', '·', 'AGENT-DRIVEN PIPELINES', '·', 'OPEN SOURCE · GPL-3.0', '·',
  ];
  return (
    <div style={{
      display: 'flex', background: bColors.ink, color: bColors.yellow,
      padding: '16px 0', borderTop: `4px solid ${bColors.ink}`, borderBottom: `4px solid ${bColors.ink}`,
      fontFamily: bDisplay, fontSize: 22, letterSpacing: 2, overflow: 'hidden', whiteSpace: 'nowrap', gap: 28,
    }}>
      {[...items, ...items].map((t, i) => (
        <span key={i} style={{ padding: '0 14px', color: t === '·' ? bColors.red : bColors.yellow }}>{t}</span>
      ))}
    </div>
  );
}

function BrutFeatures({ viewport }) {
  const items = [
    { n: '01', t: 'STREAM', d: 'JSONL events. Stable schema. Pipe to grep, jq, duckdb, or your agent. The CLI *is* the API.' },
    { n: '02', t: 'J1939',  d: 'Heavy vehicles are not an afterthought. PGNs, TP reassembly, address claim — first-class.' },
    { n: '03', t: 'UDS',    d: 'Discover services. Trace transactions. Safety guards refuse active commands on moving vehicles.' },
    { n: '04', t: 'DBC',    d: 'Provider-backed discovery. Local cache. Reverse-engineering matchers when you only have frames.' },
    { n: '05', t: 'GATEWAY',d: 'Bridge buses. Rewrite frames in flight. Replay captures with real timing or compressed.' },
    { n: '06', t: 'AGENT',  d: 'Deterministic subcommands. MCP server. Build loops with Claude, Cursor, or anything that can shell out.' },
  ];
  return (
    <section style={{ padding: sectionPadding(viewport, '60px 56px'), background: bColors.paper, borderTop: `4px solid ${bColors.ink}` }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 40, flexDirection: viewport.isMobile ? 'column' : 'row', gap: 16 }}>
        <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 64 : viewport.isTablet ? 84 : 100, margin: 0, letterSpacing: viewport.isMobile ? -2 : -3, lineHeight: 0.9, color: bColors.ink }}>
          SIX<br/>MOVES.
        </h2>
        <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 2, color: bColors.mute, textAlign: 'right' }}>
          CORE SUBCOMMANDS<br/>all composable · all emit events
        </div>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)', gap: 0,
        border: `4px solid ${bColors.ink}`, background: bColors.ink,
      }}>
        {items.map((f, i) => (
          <div key={f.n} style={{
            background: bColors.bg, padding: '28px 26px 34px', position: 'relative',
            borderRight: viewport.isMobile ? 'none' : viewport.isTablet ? (i % 2 === 0 ? `4px solid ${bColors.ink}` : 'none') : (i % 3 !== 2 ? `4px solid ${bColors.ink}` : 'none'),
            borderBottom: i < items.length - (viewport.isMobile ? 1 : viewport.isTablet ? 2 : 3) ? `4px solid ${bColors.ink}` : 'none', minHeight: 240,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
              <span style={{ fontFamily: bMono, fontWeight: 700, fontSize: 12, letterSpacing: 2 }}>NO.{f.n}</span>
              <span style={{ fontFamily: bMono, fontWeight: 700, fontSize: 12, letterSpacing: 2, color: bColors.red }}>● STABLE</span>
            </div>
            <h3 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 42 : 54, margin: '0 0 14px', letterSpacing: -2, lineHeight: 1, color: bColors.ink }}>
              {f.t}
            </h3>
            <div style={{ width: 60, height: 4, background: bColors.yellow, margin: '0 0 16px' }}/>
            <p style={{ fontFamily: bBody, fontSize: 15, lineHeight: 1.5, color: bColors.ink, margin: 0, fontWeight: 500 }}>
              {f.d}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function BrutCommand({ viewport }) {
  return (
    <section style={{ padding: sectionPadding(viewport), background: bColors.ink, color: bColors.bg, position: 'relative' }}>
      <div style={{
        position: viewport.isMobile ? 'static' : 'absolute', top: 30, right: 56, transform: viewport.isMobile ? 'none' : 'rotate(4deg)', border: `3px solid ${bColors.yellow}`,
        padding: '10px 16px', color: bColors.yellow, fontFamily: bMono, fontSize: 11, letterSpacing: 2, fontWeight: 700,
        display: 'inline-block', marginBottom: viewport.isMobile ? 20 : 0,
      }}>
        ◉ LIVE TAPE · can0 @ 250K
      </div>
      <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 3, color: bColors.yellow, marginBottom: 16 }}>
        // EXHIBIT A — ONE PIPELINE, ONE TRUTH
      </div>
      <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 54 : viewport.isTablet ? 72 : 86, letterSpacing: viewport.isMobile ? -1.5 : -3, lineHeight: 0.95, margin: '0 0 40px', color: bColors.bg }}>
        CAPTURE. DECODE.<br/>
        <span style={{ color: bColors.yellow }}>DIFF.</span> REPLAY.
      </h2>

      <div style={{ display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : '1fr 1fr', gap: 24 }}>
        <div style={{ background: bColors.bg, color: bColors.ink, padding: '24px 26px', border: `4px solid ${bColors.yellow}` }}>
          <div style={{ fontFamily: bMono, fontSize: 11, color: bColors.red, letterSpacing: 2, fontWeight: 700, marginBottom: 12 }}>
            # STEP 1 — CAPTURE + DECODE
          </div>
          <pre style={{ margin: 0, fontFamily: bMono, fontSize: viewport.isMobile ? 12 : 14, lineHeight: 1.7, color: bColors.ink, overflowX: 'auto' }}>
{`$ canarchy capture \\
    --iface can0 \\
    --decode j1939 \\
    --out run.jsonl

{"ts":"17:42:19.20","pgn":61444,
 "name":"EEC1","engine_rpm":1842.25}
{"ts":"17:42:19.22","pgn":61444,
 "name":"EEC1","engine_rpm":1847.00}
{"ts":"17:42:19.24","pgn":65262,
 "name":"ET1", "coolant_c":88}`}
          </pre>
        </div>

        <div style={{ background: bColors.yellow, color: bColors.ink, padding: '24px 26px', border: `4px solid ${bColors.bg}` }}>
          <div style={{ fontFamily: bMono, fontSize: 11, color: bColors.red, letterSpacing: 2, fontWeight: 700, marginBottom: 12 }}>
            # STEP 2 — DIFF AGAINST BASELINE
          </div>
          <pre style={{ margin: 0, fontFamily: bMono, fontSize: viewport.isMobile ? 12 : 14, lineHeight: 1.7, color: bColors.ink, overflowX: 'auto' }}>
{`$ canarchy diff \\
    baseline.jsonl run.jsonl \\
    --by pgn --by source-address

+ 0x27  UDS  diagnostic_session_ctrl
+ 0x27  UDS  security_access (seed req)
~ 0xEE  EEC1 rpm distribution shifted
- 0xF0  VDC2 stopped broadcasting`}
          </pre>
        </div>
      </div>
    </section>
  );
}

function BrutMCP({ viewport }) {
  const tools = [
    { name: 'canarchy.capture',       args: 'iface, duration, decode',     ret: 'stream<Event>' },
    { name: 'canarchy.decode',        args: 'frames[], dbc?',              ret: 'stream<Event>' },
    { name: 'canarchy.filter',        args: 'pgn?, sa?, name?',            ret: 'stream<Event>' },
    { name: 'canarchy.replay',        args: 'path, speed, loop',           ret: 'stream<Event>' },
    { name: 'canarchy.diff',          args: 'a.jsonl, b.jsonl, by[]',      ret: 'stream<Delta>' },
    { name: 'canarchy.uds.scan',      args: 'target_sa, services[]',       ret: 'stream<UdsResult>' },
    { name: 'canarchy.dbc.search',    args: 'query, providers[]',          ret: 'Bundle[]' },
    { name: 'canarchy.gateway',       args: 'src, dst, rewrite',           ret: 'stream<Event>' },
    { name: 'canarchy.generate',      args: 'dbc, signals{}',              ret: 'stream<Frame>' },
  ];

  const transcript = [
    { k: 'user', who: 'USER',   t: 'Audit the truck on can0 for 10s and flag anything that looks like an unsolicited diagnostic session.' },
    { k: 'thought', t: '↳ agent decides to capture, then filter UDS, then compare against a lane-stop guard' },
    { k: 'call', fn: 'canarchy.capture', body: '{ "iface": "can0", "duration_s": 10, "decode": "j1939" }' },
    { k: 'ret',  body: '{"type":"event.stream.start","schema":"canarchy/v1"} … 428 events' },
    { k: 'call', fn: 'canarchy.filter',  body: '{ "from": "$last", "name": ["UDS.*"] }' },
    { k: 'ret',  body: '3 matching events — all sa=0x27' },
    { k: 'call', fn: 'canarchy.uds.scan', body: '{ "target_sa": "0x27", "services": ["0x10","0x27"], "arm": false }' },
    { k: 'ret',  body: 'dry-run: 2 services would be probed · pass --arm to execute' },
    { k: 'asst', who: 'AGENT',  t: 'Flagged 3 uds.session.request from sa=0x27. Stayed in dry-run — no frames written. JSONL saved to run-0427.jsonl.' },
  ];

  return (
    <section style={{
      padding: sectionPadding(viewport), background: bColors.ink, color: bColors.bg,
      borderTop: `4px solid ${bColors.ink}`, borderBottom: `4px solid ${bColors.ink}`,
      position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', flexWrap: 'wrap', gap: 20 }}>
        <div>
          <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 3, color: bColors.yellow, fontWeight: 700, marginBottom: 14 }}>
            ■ MCP SERVER · AGENTS GET A SEAT
          </div>
          <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 56 : viewport.isTablet ? 82 : 110, letterSpacing: viewport.isMobile ? -1.5 : -3.5, lineHeight: 0.88, margin: 0, color: bColors.bg }}>
            PLUG CLAUDE<br/>
            <span style={{ color: bColors.yellow }}>STRAIGHT INTO</span><br/>
            THE CAN BUS.
          </h2>
        </div>
        <div style={{
          background: bColors.yellow, color: bColors.ink, padding: '12px 18px',
          fontFamily: bMono, fontSize: 11, fontWeight: 700, letterSpacing: 2,
          border: `4px solid ${bColors.bg}`, transform: viewport.isMobile ? 'none' : 'rotate(2deg)',
        }}>
          9 TOOLS · 1 SCHEMA · 0 GLUE CODE
        </div>
      </div>

      {/* Big serve command */}
      <div style={{
        marginTop: 40, background: bColors.yellow, color: bColors.ink,
        border: `4px solid ${bColors.bg}`, padding: '22px 26px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap',
      }}>
        <div style={{ fontFamily: bMono, fontSize: viewport.isMobile ? 15 : 22, fontWeight: 700, letterSpacing: -0.5, overflowWrap: 'anywhere' }}>
          <span style={{ color: bColors.red }}>$</span> canarchy mcp serve --bind 127.0.0.1:6969
        </div>
        <div style={{ fontFamily: bMono, fontSize: 11, letterSpacing: 2, fontWeight: 700 }}>
          WORKS WITH CLAUDE DESKTOP · CURSOR · ANY MCP CLIENT
        </div>
      </div>

      <div style={{
        marginTop: 40, display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : '1.15fr 1fr', gap: 24,
      }}>
        {/* Tool catalog */}
        <div style={{
          background: bColors.bg, color: bColors.ink, border: `4px solid ${bColors.yellow}`,
          padding: 0,
        }}>
          <div style={{
            background: bColors.yellow, color: bColors.ink,
            padding: '12px 18px', fontFamily: bDisplay, fontSize: 16, letterSpacing: 2,
            borderBottom: `4px solid ${bColors.ink}`,
          }}>
            TOOL CATALOG · canarchy.* (9 tools, all stream)
          </div>
          <div style={{ fontFamily: bMono, fontSize: 13, lineHeight: 1.75 }}>
            {tools.map((t, i) => (
              <div key={t.name} style={{
                display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : '1.3fr 1.6fr 1fr',
                gap: 12, padding: '10px 18px',
                background: i % 2 ? 'transparent' : 'rgba(11,11,11,0.04)',
                borderBottom: i < tools.length - 1 ? `1px dashed ${bColors.ink}` : 'none',
              }}>
                <span style={{ fontWeight: 700, color: bColors.ink }}>{t.name}</span>
                <span style={{ color: bColors.mute }}>{t.args}</span>
                <span style={{ color: bColors.red, fontWeight: 700, textAlign: viewport.isMobile ? 'left' : 'right' }}>{t.ret}</span>
              </div>
            ))}
          </div>
          <div style={{
            borderTop: `4px solid ${bColors.ink}`, padding: '12px 18px',
            fontFamily: bMono, fontSize: 11, color: bColors.ink, letterSpacing: 1, fontWeight: 700,
            display: 'flex', justifyContent: 'space-between', background: bColors.paper,
            flexDirection: viewport.isMobile ? 'column' : 'row', gap: 8,
          }}>
            <span>■ ALL EVENTS: canarchy/v1</span>
            <span style={{ color: bColors.mute }}>◆ GUARDS: PLANNED</span>
            <span>■ STREAMING</span>
          </div>
        </div>

        {/* Agent transcript */}
        <div style={{
          background: bColors.bg, color: bColors.ink, border: `4px solid ${bColors.bg}`,
          position: 'relative',
        }}>
          <div style={{
            background: bColors.red, color: bColors.bg,
            padding: '12px 18px', fontFamily: bDisplay, fontSize: 16, letterSpacing: 2,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>AGENT TRANSCRIPT · LIVE</span>
            <span style={{ fontFamily: bMono, fontSize: 11, fontWeight: 700 }}>claude ↔ canarchy</span>
          </div>
          <div style={{ fontFamily: bMono, fontSize: 12.5, lineHeight: 1.7, padding: '18px 20px' }}>
            {transcript.map((row, i) => {
              if (row.k === 'user') return (
                <div key={i} style={{ marginBottom: 10 }}>
                  <span style={{ background: bColors.ink, color: bColors.yellow, padding: '2px 8px', fontWeight: 700, letterSpacing: 1, fontSize: 10 }}>{row.who}</span>{' '}
                  <span style={{ color: bColors.ink }}>{row.t}</span>
                </div>
              );
              if (row.k === 'thought') return (
                <div key={i} style={{ color: bColors.mute, marginBottom: 8, fontStyle: 'italic' }}>{row.t}</div>
              );
              if (row.k === 'call') return (
                <div key={i} style={{ marginBottom: 4 }}>
                  <span style={{ color: bColors.red, fontWeight: 700 }}>→ call</span>{' '}
                  <span style={{ color: bColors.ink, fontWeight: 700 }}>{row.fn}</span>{' '}
                  <span style={{ color: bColors.mute }}>{row.body}</span>
                </div>
              );
              if (row.k === 'ret') return (
                <div key={i} style={{ marginBottom: 10, paddingLeft: 18, color: bColors.mute }}>
                  <span style={{ color: bColors.ink, fontWeight: 700 }}>←</span> {row.body}
                </div>
              );

              if (row.k === 'asst') return (
                <div key={i} style={{ marginTop: 8 }}>
                  <span style={{ background: bColors.red, color: bColors.bg, padding: '2px 8px', fontWeight: 700, letterSpacing: 1, fontSize: 10 }}>{row.who}</span>{' '}
                  <span style={{ color: bColors.ink }}>{row.t}</span>
                </div>
              );
              return null;
            })}
          </div>
        </div>
      </div>

      <div style={{
        marginTop: 32, display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)', gap: 0,
        border: `4px solid ${bColors.bg}`,
      }}>
        {[
          { h: 'DETERMINISTIC', d: 'Same inputs in, same JSONL out. Agents can loop without drift.' },
          { h: 'STREAMING', d: 'Tools return event streams. No 10k-token blobs, no truncation.' },
          { h: 'DRY-RUN BY DEFAULT', d: 'Active commands require an explicit --arm. Guard framework (speed / ignition / session) is on the roadmap.', planned: true },
        ].map((b, i) => (
          <div key={b.h} style={{
            background: i === 1 ? bColors.yellow : bColors.bg,
            color: bColors.ink, padding: '20px 22px',
            borderLeft: viewport.isMobile ? 'none' : i > 0 ? `4px solid ${bColors.bg}` : 'none',
            borderTop: viewport.isMobile && i > 0 ? `4px solid ${bColors.bg}` : 'none',
          }}>
            <div style={{ fontFamily: bDisplay, fontSize: 22, letterSpacing: -0.5, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 10 }}>
              {b.h}
              {b.planned && (
                <span style={{
                  fontFamily: bMono, fontSize: 9, letterSpacing: 2, fontWeight: 700,
                  background: bColors.ink, color: bColors.yellow, padding: '2px 6px',
                }}>PLANNED</span>
              )}
            </div>
            <div style={{ fontFamily: bMono, fontSize: 12, lineHeight: 1.55, color: bColors.ink }}>{b.d}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function BrutMatrix({ viewport }) {
  const tools = ['CANarchy', 'can-utils', 'python-can', 'cantools', 'SavvyCAN', 'Caring Caribou', 'TruckDevil'];
  const rows = [
    ['CLI-first',            [1,1,0,1,0,1,0]],
    ['JSONL events',         [1,0,0,0,0,0,0]],
    ['Pipe composition',     [1,0,0,0,0,0,0]],
    ['J1939 native',         [1,0,0,0,0,0,1]],
    ['UDS workflows',        [1,0,0,0,0,1,0]],
    ['DBC decode/encode',    [1,0,0,1,1,0,0]],
    ['Provider-backed DBC',  [1,0,0,0,0,0,0]],
    ['Agent / MCP',          [1,0,0,0,0,0,0]],
  ];
  return (
    <section style={{ padding: sectionPadding(viewport), background: bColors.bg }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 30, flexDirection: viewport.isMobile ? 'column' : 'row', gap: 16 }}>
        <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 56 : viewport.isTablet ? 72 : 86, letterSpacing: viewport.isMobile ? -1.5 : -3, lineHeight: 0.9, margin: 0, color: bColors.ink }}>
          THE<br/>MATRIX.
        </h2>
        <div style={{ fontFamily: bMono, fontSize: 12, color: bColors.mute, textAlign: 'right', letterSpacing: 1 }}>
          FIRST-CLASS ONLY · NO HALFWAY<br/>■ = shipped · □ = not a focus
        </div>
      </div>
      <div style={{ border: `4px solid ${bColors.ink}`, background: bColors.ink, overflowX: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr repeat(7, 1fr)', minWidth: 820 }}>
          <div style={{ background: bColors.yellow, color: bColors.ink, padding: '14px 18px', fontFamily: bDisplay, fontSize: 14, letterSpacing: 2 }}>WORKFLOW</div>
          {tools.map((t, i) => (
            <div key={t} style={{
              background: i === 0 ? bColors.red : bColors.ink,
              color: i === 0 ? bColors.bg : bColors.bg,
              padding: '14px 10px', textAlign: 'center',
              fontFamily: bDisplay, fontSize: 13, letterSpacing: 1,
              borderLeft: `2px solid ${bColors.ink}`,
            }}>{t}</div>
          ))}
        </div>
        {rows.map((r, ri) => (
          <div key={r[0]} style={{ display: 'grid', gridTemplateColumns: '2fr repeat(7, 1fr)', background: bColors.bg, borderTop: `2px solid ${bColors.ink}`, minWidth: 820 }}>
            <div style={{ padding: '14px 18px', fontFamily: bBody, fontWeight: 700, fontSize: 15, color: bColors.ink }}>{r[0]}</div>
            {r[1].map((v, ci) => (
              <div key={ci} style={{
                padding: '14px 10px', textAlign: 'center',
                background: ci === 0 && v === 1 ? bColors.yellow : bColors.bg,
                color: bColors.ink, fontFamily: bDisplay, fontSize: 22, letterSpacing: 1,
                borderLeft: `2px solid ${bColors.ink}`,
              }}>{v ? '■' : '·'}</div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function BrutManifesto({ viewport }) {
  const points = [
    'ONE RUNTIME, MANY DOORS',
    'CAPTURE FIRST, ASK QUESTIONS LATER',
    'J1939 IS NOT A PLUGIN',
    'AGENTS DRIVE \u00b7 HUMANS RIDE',
    'SCRIPT IT, DON\u2019T CLICK IT',
    'PoC || GTFO',
  ];
  return (
    <section style={{ background: bColors.yellow, color: bColors.ink, padding: viewport.isMobile ? '56px 18px' : viewport.isTablet ? '68px 28px' : '80px 56px', borderTop: `4px solid ${bColors.ink}`, borderBottom: `4px solid ${bColors.ink}`, position: 'relative' }}>
      <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 3, color: bColors.red, fontWeight: 700, marginBottom: 14 }}>
        ▲▲▲ MANIFESTO ▲▲▲
      </div>
      <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 58 : viewport.isTablet ? 84 : 120, lineHeight: 0.9, letterSpacing: viewport.isMobile ? -1.5 : -4, margin: '0 0 40px' }}>
        SIX RULES.<br/>ONE EXCEPTION: YOU.
      </h2>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : 'repeat(2, 1fr)', gap: 0, borderTop: `4px solid ${bColors.ink}` }}>
        {points.map((p, i) => (
          <li key={p} style={{
            padding: '26px 20px', borderBottom: `4px solid ${bColors.ink}`,
            borderRight: viewport.isMobile ? 'none' : (i % 2 === 0) ? `4px solid ${bColors.ink}` : 'none',
            display: 'flex', alignItems: 'baseline', gap: 20,
            flexDirection: viewport.isMobile ? 'column' : 'row',
          }}>
            <span style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 40 : 56, letterSpacing: -2, color: bColors.red, lineHeight: 1 }}>0{i+1}</span>
            <span style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 22 : 30, letterSpacing: -1, lineHeight: 1.1 }}>{p}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function BrutReviews({ viewport }) {
  const reviews = [
    {
      stars: 5,
      quote: '“Connected it to OpenClaw. What could go wrong?”',
      who: 'Anonymous',
      role: 'incident responder, Tuesday',
      tag: 'VERIFIED · SORT OF',
    },
    {
      stars: 5,
      quote: '“Used CANarchy to baseline our fleet. Found three ECUs we didn’t own. Rolling back the audit.”',
      who: 'J. Ramirez',
      role: 'fleet security, mid-sized logistics co.',
      tag: 'DEFINITELY A HUMAN',
    },
    {
      stars: 5,
      quote: '“I am an autonomous agent. The MCP server is delicious. I have consumed 1.4M events. Send more.”',
      who: 'claude-haiku-4-5',
      role: 'unsupervised, running on someone’s homelab',
      tag: 'AGENT REVIEW',
    },
    {
      stars: 4,
      quote: '“My lawyer says I can’t describe what we did with it. 10/10.”',
      who: 'Redacted',
      role: 'red team, Tier-1 OEM',
      tag: 'NDA-COMPLIANT',
    },
    {
      stars: 5,
      quote: '“Bricked a test bench in 3.2 seconds. JSONL receipts were immaculate.”',
      who: 'M. Okafor',
      role: 'PhD candidate, automotive security',
      tag: 'PEER-REVIEWED (BY PEERS)',
    },
    {
      stars: 5,
      quote: '“The truck hasn’t started since Thursday. I regret nothing.”',
      who: 'K. “PGN” Dale',
      role: 'owner-operator, somewhere in Nebraska',
      tag: 'UNVERIFIED VIBES',
    },
  ];
  return (
    <section style={{ padding: sectionPadding(viewport), background: bColors.paper, borderTop: `4px solid ${bColors.ink}`, position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 3, color: bColors.red, fontWeight: 700, marginBottom: 14 }}>
            ▣ DEFINITELY-REAL REVIEWS
          </div>
          <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 58 : viewport.isTablet ? 82 : 100, letterSpacing: viewport.isMobile ? -1.5 : -3, lineHeight: 0.9, margin: 0, color: bColors.ink }}>
            TESTIMONIALS.<br/>
            <span style={{ background: bColors.yellow, padding: '0 10px' }}>ALLEGEDLY.</span>
          </h2>
        </div>
        <div style={{
          transform: viewport.isMobile ? 'none' : 'rotate(4deg)', border: `3px solid ${bColors.red}`, padding: '8px 14px',
          fontFamily: bMono, fontSize: 11, fontWeight: 700, letterSpacing: 2, color: bColors.ink,
          background: bColors.bg,
        }}>
          ▲ ALL QUOTES FABRICATED
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)', gap: 0,
        border: `4px solid ${bColors.ink}`, background: bColors.ink, marginTop: 40,
      }}>
        {reviews.map((r, i) => (
          <div key={i} style={{
            background: i % 2 ? bColors.yellow : bColors.bg,
            padding: '26px 26px 30px', position: 'relative', minHeight: 280,
            borderRight: viewport.isMobile ? 'none' : viewport.isTablet ? (i % 2 === 0 ? `4px solid ${bColors.ink}` : 'none') : (i % 3 !== 2 ? `4px solid ${bColors.ink}` : 'none'),
            borderBottom: i < reviews.length - (viewport.isMobile ? 1 : viewport.isTablet ? 2 : 3) ? `4px solid ${bColors.ink}` : 'none',
          }}>
            <div style={{
              fontFamily: bDisplay, fontSize: 22, color: bColors.red, letterSpacing: 2, marginBottom: 16,
            }}>
              {'★'.repeat(r.stars)}<span style={{ color: bColors.mute }}>{'☆'.repeat(5 - r.stars)}</span>
            </div>
            <p style={{
              fontFamily: bDisplay, fontSize: 22, lineHeight: 1.15, letterSpacing: -0.5,
              margin: '0 0 22px', color: bColors.ink,
            }}>
              {r.quote}
            </p>
            <div style={{ width: 40, height: 3, background: bColors.ink, marginBottom: 12 }}/>
            <div style={{ fontFamily: bMono, fontSize: 12, color: bColors.ink, fontWeight: 700, letterSpacing: 1 }}>
              {r.who}
            </div>
            <div style={{ fontFamily: bMono, fontSize: 11, color: bColors.mute, marginTop: 2 }}>
              {r.role}
            </div>
            <div style={{
              position: 'absolute', top: 18, right: 18,
              background: bColors.ink, color: bColors.yellow,
              fontFamily: bMono, fontSize: 9, fontWeight: 700, letterSpacing: 2,
              padding: '3px 8px',
            }}>{r.tag}</div>
          </div>
        ))}
      </div>

      <div style={{
        marginTop: 18, fontFamily: bMono, fontSize: 11, color: bColors.mute, letterSpacing: 1, textAlign: 'right',
      }}>
        * Any resemblance to real people, fleets, or incidents is entirely intentional and also fully deniable.
      </div>
    </section>
  );
}

function BrutInstall({ viewport }) {
  return (
    <section style={{ padding: viewport.isMobile ? '56px 18px' : viewport.isTablet ? '68px 28px' : '80px 56px', background: bColors.bg, position: 'relative' }}>
      <div style={{ display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : '1fr 1.3fr', gap: 48, alignItems: 'stretch' }}>
        <div>
          <div style={{ fontFamily: bMono, fontSize: 12, letterSpacing: 3, color: bColors.red, fontWeight: 700 }}>
            ▣ INSTALL / RUN
          </div>
          <h2 style={{ fontFamily: bDisplay, fontSize: viewport.isMobile ? 56 : viewport.isTablet ? 72 : 92, lineHeight: 0.9, letterSpacing: viewport.isMobile ? -1.5 : -3, margin: '16px 0 26px', color: bColors.ink }}>
            THREE<br/>COMMANDS.<br/>
            <span style={{ background: bColors.yellow, padding: '0 10px' }}>ZERO</span> FLUFF.
          </h2>
          <p style={{ fontFamily: bBody, fontSize: 17, lineHeight: 1.5, color: bColors.ink, maxWidth: 460, fontWeight: 500 }}>
            Plug in a USB CAN interface, point it at a log file, or spin up a virtual bus.
            You&rsquo;ll have your first JSONL event before your coffee is cold.
          </p>
        </div>
        <div style={{ background: bColors.ink, color: bColors.bg, padding: viewport.isMobile ? '24px 18px' : '30px 32px', border: `4px solid ${bColors.ink}`, position: 'relative' }}>
          <div style={{ position: 'absolute', top: -14, left: 24, background: bColors.red, color: bColors.bg, fontFamily: bMono, fontSize: 11, letterSpacing: 2, fontWeight: 700, padding: '4px 10px' }}>
            $ ZSH · canarchy v0.4.1
          </div>
          <pre style={{ margin: 0, fontFamily: bMono, fontSize: viewport.isMobile ? 12 : 15, lineHeight: 1.9, color: bColors.bg, overflowX: 'auto' }}>
<span style={{ color: bColors.mute }}># 1. install</span>{'\n'}
<span style={{ color: bColors.yellow }}>➜</span> pip install canarchy{'\n\n'}
<span style={{ color: bColors.mute }}># 2. bring up a virtual bus</span>{'\n'}
<span style={{ color: bColors.yellow }}>➜</span> canarchy transport up --backend virtual{'\n\n'}
<span style={{ color: bColors.mute }}># 3. stream J1939 events as JSONL</span>{'\n'}
<span style={{ color: bColors.yellow }}>➜</span> canarchy capture --decode j1939 --pretty{'\n\n'}
<span style={{ color: bColors.mute }}># 4. (optional) let an agent drive it</span>{'\n'}
<span style={{ color: bColors.yellow }}>➜</span> canarchy mcp serve --bind 127.0.0.1:7801{'\n'}
          </pre>
        </div>
      </div>
    </section>
  );
}

const footerLinks = {
  DOCS: [
    { label: 'Getting Started', href: siteBase + '/docs/getting_started' },
    { label: 'Command Spec',    href: siteBase + '/docs/command_spec' },
    { label: 'Event Schema',    href: siteBase + '/docs/event-schema' },
    { label: 'Matrix',          href: siteBase + '/docs/feature-matrix' },
  ],
  GUIDE: [
    { label: 'Backends',   href: siteBase + '/docs/backends' },
    { label: 'J1939',      href: siteBase + '/docs/tutorials/j1939_heavy_vehicle' },
    { label: 'UDS',        href: siteBase + '/docs/tutorials' },
    { label: 'Tutorials',  href: siteBase + '/docs/tutorials' },
  ],
  DEV: [
    { label: 'Architecture', href: siteBase + '/docs/architecture' },
    { label: 'Design',        href: siteBase + '/docs/overview' },
    { label: 'Release',        href: siteBase + '/docs/release' },
    { label: 'TUI',           href: siteBase + '/docs/tui_plan' },
  ],
  SOCIAL: [
    { label: 'GitHub',      href: 'https://github.com/hexsecs/canarchy' },
    { label: 'Issues',      href: 'https://github.com/hexsecs/canarchy/issues' },
    { label: 'Discussions', href: 'https://github.com/hexsecs/canarchy/discussions' },
    { label: 'Agents',      href: siteBase + '/docs/agents' },
  ],
};

function BrutFooter({ viewport }) {
  return (
    <>
      <CautionStripe h={14} flip/>
      <footer style={{ background: bColors.ink, color: bColors.bg, padding: viewport.isMobile ? '42px 18px 32px' : viewport.isTablet ? '50px 28px 36px' : '50px 56px 40px', fontFamily: bBody }}>
        <div style={{ display: 'grid', gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : '2fr 1fr 1fr 1fr 1fr', gap: 40 }}>
          <div>
            <div style={{ fontFamily: bDisplay, fontSize: 44, letterSpacing: -1.5, color: bColors.yellow, lineHeight: 1 }}>CAN/ARCHY</div>
            <div style={{ marginTop: 14, fontFamily: bMono, fontSize: 12, lineHeight: 1.7, color: '#d8d3c5' }}>
              STREAM-FIRST CAN ANALYSIS RUNTIME.<br/>
              OPEN SOURCE · GPL-3.0 · BUILT BY hexsecs.<br/>
              FOR RESEARCHERS, NOT DEALERSHIPS.
            </div>
          </div>
          {Object.entries(footerLinks).map(([h, links]) => (
            <div key={h}>
              <div style={{ fontFamily: bDisplay, fontSize: 14, letterSpacing: 2, color: bColors.yellow, marginBottom: 14 }}>{h}</div>
              {links.map(l => (
                <a
                  key={l.label}
                  href={l.href}
                  target={l.href.startsWith('http') ? '_blank' : undefined}
                  rel={l.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                  style={{
                    display: 'block',
                    fontFamily: bMono, fontSize: 12, marginBottom: 7,
                    color: '#d8d3c5', textDecoration: 'none',
                  }}
                >
                  {l.label}
                </a>
              ))}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 50, paddingTop: 20, borderTop: `2px solid ${bColors.yellow}`, display: 'flex', justifyContent: 'space-between', fontFamily: bMono, fontSize: 11, letterSpacing: 2, color: '#b0ab9e', flexDirection: viewport.isMobile ? 'column' : 'row', gap: 10 }}>
          <span>HEXSECS / CANARCHY · GPL-3.0 · 2026</span>
          <span>TRY BUS STUFF · RECORD EVERYTHING</span>
        </div>
      </footer>
    </>
  );
}

function SiteBrutalist() {
  const viewport = useViewport();

  return (
    <div style={{
      width: '100%', height: '100%', background: bColors.bg, color: bColors.ink,
      fontFamily: bBody, position: 'relative', overflowX: 'hidden',
    }}>
      <BrutNav viewport={viewport}/>
      <BrutHero viewport={viewport}/>
      <BrutTicker/>
      <BrutFeatures viewport={viewport}/>
      <BrutCommand viewport={viewport}/>
      <BrutMCP viewport={viewport}/>
      <BrutMatrix viewport={viewport}/>
      <BrutReviews viewport={viewport}/>
      <BrutManifesto viewport={viewport}/>
      <BrutInstall viewport={viewport}/>
      <BrutFooter viewport={viewport}/>
    </div>
  );
}

window.SiteBrutalist = SiteBrutalist;
