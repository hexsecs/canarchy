const RELEASE_VERSION = '0.7.0';
const RELEASE_MONTH = 'MAY 2026';
const RELEASE_ISSUE = RELEASE_VERSION.replace(/^0\.(\d+)\.(.+)$/, (_, maj, rest) => maj.padStart(2, '0') + '.' + rest);
const bColors = {
  bg: '#f3efe4',
  ink: '#0b0b0b',
  paper: '#faf6eb',
  yellow: '#ffd400',
  red: '#e0301e',
  line: '#0b0b0b',
  mute: '#555048'
};
const bDisplay = "'Archivo Black', 'Archivo', ui-sans-serif, system-ui";
const bBody = "'Archivo', ui-sans-serif, system-ui";
const bMono = "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, monospace";
const siteBase = '/canarchy';
const {
  useEffect,
  useState
} = React;
function useViewport() {
  const getWidth = () => typeof window === 'undefined' ? 1280 : window.innerWidth;
  const [width, setWidth] = useState(getWidth);
  useEffect(() => {
    const onResize = () => setWidth(getWidth());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return {
    width,
    isMobile: width < 760,
    isCompactMobile: width < 430,
    isNarrowMobile: width < 390,
    isTablet: width >= 760 && width < 1100
  };
}
function sectionPadding(viewport, desktop = '70px 56px') {
  if (viewport.isMobile) return '42px 18px';
  if (viewport.isTablet) return '56px 28px';
  return desktop;
}
function CautionStripe({
  h = 24,
  flip = false
}) {
  return React.createElement("div", {
    style: {
      height: h,
      background: `repeating-linear-gradient(${flip ? '-45deg' : '45deg'}, ${bColors.yellow} 0 20px, ${bColors.ink} 20px 40px)`
    }
  });
}
const navLinks = [{
  label: 'DOCS',
  href: siteBase + '/docs/getting_started'
}, {
  label: 'COMMANDS',
  href: siteBase + '/docs/command_spec'
}, {
  label: 'J1939',
  href: siteBase + '/docs/tutorials/j1939_heavy_vehicle'
}, {
  label: 'AGENTS',
  href: siteBase + '/docs/agents'
}, {
  label: 'GITHUB',
  href: 'https://github.com/hexsecs/canarchy'
}];
function BrutNav({
  viewport
}) {
  const compact = viewport.isMobile;
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  useEffect(() => {
    if (!compact) setIsMenuOpen(false);
  }, [compact]);
  return React.createElement(React.Fragment, null, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'stretch',
      justifyContent: 'space-between',
      flexDirection: compact ? 'column' : 'row',
      background: bColors.ink,
      color: bColors.bg,
      borderBottom: `4px solid ${bColors.ink}`
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: compact ? 'stretch' : 'center',
      gap: 0,
      flexDirection: compact ? 'column' : 'row',
      flex: compact ? '1 1 auto' : '0 0 auto'
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'stretch',
      justifyContent: 'space-between'
    }
  }, React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: compact ? '16px 18px' : '18px 22px',
      fontFamily: bDisplay,
      fontSize: compact ? 20 : 22,
      letterSpacing: 1,
      borderRight: compact ? 'none' : `4px solid ${bColors.ink}`,
      borderBottom: compact ? `4px solid ${bColors.ink}` : 'none',
      flex: compact ? '1 1 auto' : '0 0 auto'
    }
  }, "CAN/ARCHY"), compact && React.createElement("button", {
    type: "button",
    "aria-label": isMenuOpen ? 'Close navigation menu' : 'Open navigation menu',
    "aria-expanded": isMenuOpen,
    "aria-controls": "homepage-mobile-nav",
    onClick: () => setIsMenuOpen(open => !open),
    style: {
      appearance: 'none',
      border: 'none',
      borderLeft: `4px solid ${bColors.ink}`,
      borderBottom: `4px solid ${bColors.ink}`,
      background: isMenuOpen ? bColors.red : bColors.paper,
      color: bColors.ink,
      padding: '0 18px',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: 72
    }
  }, React.createElement("span", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5
    }
  }, [0, 1, 2].map(line => React.createElement("span", {
    key: line,
    style: {
      width: 24,
      height: 3,
      background: bColors.ink,
      display: 'block'
    }
  }))))), React.createElement("div", {
    style: {
      padding: compact ? '14px 18px' : '18px 22px',
      fontFamily: bMono,
      fontSize: compact ? 10 : 11,
      letterSpacing: 2,
      color: '#f3efe4'
    }
  }, "STREAM-FIRST \xB7 AGENT-FIRST \xB7 J1939-FIRST")), React.createElement("div", {
    id: compact ? 'homepage-mobile-nav' : undefined,
    style: {
      display: compact ? isMenuOpen ? 'flex' : 'none' : 'flex',
      alignItems: 'center',
      flexWrap: 'wrap',
      width: compact ? '100%' : 'auto',
      borderTop: compact ? `4px solid ${bColors.bg}` : 'none'
    }
  }, navLinks.map(link => React.createElement("a", {
    key: link.label,
    href: link.href,
    target: link.label === 'GITHUB' ? '_blank' : undefined,
    rel: link.label === 'GITHUB' ? 'noopener noreferrer' : undefined,
    onClick: () => {
      if (compact) setIsMenuOpen(false);
    },
    style: {
      padding: compact ? '14px 16px' : '18px 20px',
      fontFamily: bBody,
      fontWeight: 800,
      fontSize: compact ? 12 : 13,
      letterSpacing: 2,
      borderLeft: compact ? 'none' : `2px solid ${bColors.bg}`,
      borderTop: compact ? `2px solid ${bColors.bg}` : 'none',
      cursor: 'pointer',
      background: link.label === 'GITHUB' ? bColors.red : 'transparent',
      color: bColors.bg,
      textDecoration: 'none',
      display: 'block',
      flex: compact ? '1 1 100%' : '0 0 auto',
      textAlign: compact ? 'center' : 'left'
    }
  }, link.label)))), React.createElement(CautionStripe, {
    h: 14
  }));
}
function BrutHero({
  viewport
}) {
  const stacked = viewport.isMobile;
  return React.createElement("section", {
    style: {
      padding: viewport.isMobile ? '42px 18px 26px' : viewport.isTablet ? '56px 28px 30px' : '60px 56px 30px',
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      position: stacked ? 'static' : 'absolute',
      top: 80,
      right: stacked ? 'auto' : 0,
      left: stacked ? 'auto' : 'auto',
      transform: stacked ? 'none' : 'rotate(9deg)',
      fontFamily: bMono,
      fontSize: 12,
      color: bColors.ink,
      border: `3px solid ${bColors.red}`,
      padding: '10px 18px',
      background: bColors.paper,
      letterSpacing: 2,
      fontWeight: 700,
      display: 'inline-block',
      marginBottom: stacked ? 18 : 0,
      marginLeft: stacked ? 0 : 'auto'
    }
  }, React.createElement("div", {
    style: {
      color: bColors.red
    }
  }, "\u25B2 ADVISORY"), React.createElement("div", null, "FUZZ AROUND \xB7 FIND OUT")), React.createElement("div", {
    style: {
      display: 'flex',
      gap: 0,
      marginBottom: 30,
      fontFamily: bMono,
      fontSize: 11,
      flexWrap: 'wrap'
    }
  }, React.createElement("span", {
    style: {
      background: bColors.ink,
      color: bColors.yellow,
      padding: '4px 10px',
      letterSpacing: 2,
      fontWeight: 700
    }
  }, "ISSUE ", RELEASE_ISSUE), React.createElement("span", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '4px 10px',
      letterSpacing: 2,
      fontWeight: 700
    }
  }, RELEASE_MONTH), React.createElement("span", {
    style: {
      background: bColors.paper,
      color: bColors.ink,
      padding: '4px 10px',
      letterSpacing: 2,
      fontWeight: 700,
      border: `2px solid ${bColors.ink}`
    }
  }, "FREE \xB7 TAKE ONE")), React.createElement("h1", {
    style: {
      fontFamily: bDisplay,
      fontSize: stacked ? viewport.isNarrowMobile ? 62 : viewport.isCompactMobile ? 70 : 82 : viewport.isTablet ? 150 : 220,
      lineHeight: 0.82,
      letterSpacing: stacked ? -2 : -6,
      margin: 0,
      color: bColors.ink,
      textTransform: 'uppercase'
    }
  }, "The bus", React.createElement("br", null), React.createElement("span", {
    style: {
      background: bColors.yellow,
      padding: stacked ? '0 8px' : '0 14px',
      marginLeft: stacked ? -8 : -14
    }
  }, "doesn't"), React.createElement("br", null), "lie."), React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: stacked ? '1fr' : viewport.isTablet ? '1fr' : '1.3fr 1fr',
      gap: stacked ? 24 : 56,
      marginTop: 50,
      alignItems: 'start'
    }
  }, React.createElement("p", {
    style: {
      fontFamily: bBody,
      fontSize: stacked ? viewport.isCompactMobile ? 17 : 18 : 22,
      lineHeight: 1.35,
      color: bColors.ink,
      margin: 0,
      fontWeight: 500,
      maxWidth: 640
    }
  }, "CANarchy is an ", React.createElement("b", null, "open, stream-first runtime"), " for analyzing and manipulating CAN and J1939 buses. Every command emits a canonical JSONL event. Every event is replayable. Nothing is hidden behind a GUI, a license key, or a dongle."), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      lineHeight: 1.8,
      color: bColors.ink,
      borderLeft: `4px solid ${bColors.ink}`,
      paddingLeft: 16
    }
  }, React.createElement("div", {
    style: {
      color: bColors.red,
      fontWeight: 700,
      letterSpacing: 2,
      marginBottom: 8
    }
  }, "WHAT THIS IS"), "A toolkit for security researchers, red teams,", React.createElement("br", null), "fleet auditors, OSS tinkerers, and the", React.createElement("br", null), "occasional agent operating ", React.createElement("i", null, "without supervision."), React.createElement("br", null), React.createElement("br", null), React.createElement("div", {
    style: {
      color: bColors.red,
      fontWeight: 700,
      letterSpacing: 2,
      marginBottom: 8
    }
  }, "WHAT IT IS NOT"), "A replacement for can-utils, python-can,", React.createElement("br", null), "SavvyCAN, or common sense.")), React.createElement("div", {
    style: {
      display: 'flex',
      gap: 0,
      marginTop: 50,
      flexWrap: 'wrap',
      alignItems: 'stretch'
    }
  }, React.createElement("a", {
    href: "#",
    onClick: e => {
      e.preventDefault();
      navigator.clipboard?.writeText('pip install canarchy');
    },
    style: {
      background: bColors.ink,
      color: bColors.yellow,
      padding: stacked ? viewport.isCompactMobile ? '16px 18px' : '18px 22px' : '22px 30px',
      fontFamily: bDisplay,
      fontSize: stacked ? viewport.isCompactMobile ? 17 : 18 : 20,
      letterSpacing: 1,
      textDecoration: 'none',
      border: `4px solid ${bColors.ink}`,
      textTransform: 'uppercase',
      width: stacked ? '100%' : 'auto',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, "pip install canarchy \u2192"), React.createElement("a", {
    href: siteBase + '/docs/getting_started',
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: stacked ? viewport.isCompactMobile ? '16px 18px' : '18px 22px' : '22px 30px',
      fontFamily: bDisplay,
      fontSize: stacked ? viewport.isCompactMobile ? 17 : 18 : 20,
      letterSpacing: 1,
      textDecoration: 'none',
      border: `4px solid ${bColors.ink}`,
      borderLeft: stacked ? `4px solid ${bColors.ink}` : 'none',
      borderTop: stacked ? 'none' : undefined,
      textTransform: 'uppercase',
      width: stacked ? '100%' : 'auto',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, "Read the Docs"), React.createElement("a", {
    href: "https://github.com/hexsecs/canarchy",
    target: "_blank",
    rel: "noopener noreferrer",
    style: {
      background: bColors.paper,
      color: bColors.ink,
      padding: stacked ? viewport.isCompactMobile ? '16px 18px' : '18px 22px' : '22px 30px',
      fontFamily: bDisplay,
      fontSize: stacked ? viewport.isCompactMobile ? 17 : 18 : 20,
      letterSpacing: 1,
      textDecoration: 'none',
      border: `4px solid ${bColors.ink}`,
      borderLeft: stacked ? `4px solid ${bColors.ink}` : 'none',
      borderTop: stacked ? 'none' : undefined,
      textTransform: 'uppercase',
      width: stacked ? '100%' : 'auto',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, "\u2605 Star It")));
}
function BrutTicker({
  viewport
}) {
  const fontSize = viewport.isNarrowMobile ? 16 : viewport.isCompactMobile ? 18 : 22;
  const gap = viewport.isCompactMobile ? 18 : 28;
  const items = ['J1939 NATIVE', '·', 'JSONL WIRE FORMAT', '·', 'MCP SERVER', '·', 'UDS DISCOVERY', '·', 'DBC PROVIDERS', '·', 'RATE-CONTROLLED REPLAY', '·', 'FRAME GATEWAY', '·', 'ACTIVE-COMMAND SAFETY', '·', 'AGENT-DRIVEN PIPELINES', '·', 'OPEN SOURCE · GPL-3.0', '·'];
  return React.createElement("div", {
    style: {
      display: 'flex',
      background: bColors.ink,
      color: bColors.yellow,
      padding: '16px 0',
      borderTop: `4px solid ${bColors.ink}`,
      borderBottom: `4px solid ${bColors.ink}`,
      fontFamily: bDisplay,
      fontSize,
      letterSpacing: viewport.isCompactMobile ? 1 : 2,
      overflow: 'hidden',
      whiteSpace: 'nowrap',
      gap
    }
  }, [...items, ...items].map((t, i) => React.createElement("span", {
    key: i,
    style: {
      padding: viewport.isCompactMobile ? '0 10px' : '0 14px',
      color: t === '·' ? bColors.red : bColors.yellow
    }
  }, t)));
}
function BrutFeatures({
  viewport
}) {
  const items = [{
    n: '01',
    t: 'STREAM',
    d: 'JSONL events. Stable schema. Pipe to grep, jq, duckdb, or your agent. The CLI *is* the API.'
  }, {
    n: '02',
    t: 'J1939',
    d: 'Heavy vehicles are not an afterthought. PGNs, TP reassembly, address claim — first-class.'
  }, {
    n: '03',
    t: 'UDS',
    d: 'Discover services. Trace transactions. Every active command is gated behind --ack-active, --dry-run, and a typed YES.'
  }, {
    n: '04',
    t: 'DBC',
    d: 'Provider-backed discovery. Local cache. Reverse-engineering matchers when you only have frames.'
  }, {
    n: '05',
    t: 'GATEWAY',
    d: 'Bridge buses. Rewrite frames in flight. Replay captures with real timing or compressed.'
  }, {
    n: '06',
    t: 'AGENT',
    d: 'Deterministic subcommands. MCP server. Build loops with Claude, Cursor, or anything that can shell out.'
  }];
  return React.createElement("section", {
    style: {
      padding: sectionPadding(viewport, '60px 56px'),
      background: bColors.paper,
      borderTop: `4px solid ${bColors.ink}`
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      marginBottom: 40,
      flexDirection: viewport.isMobile ? 'column' : 'row',
      gap: 16
    }
  }, React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 46 : viewport.isCompactMobile ? 52 : 64 : viewport.isTablet ? 84 : 100,
      margin: 0,
      letterSpacing: viewport.isMobile ? -2 : -3,
      lineHeight: 0.9,
      color: bColors.ink
    }
  }, "SIX", React.createElement("br", null), "MOVES."), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 2,
      color: bColors.mute,
      textAlign: 'right'
    }
  }, "CORE SUBCOMMANDS", React.createElement("br", null), "all composable \xB7 all emit events")), React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
      gap: 0,
      border: `4px solid ${bColors.ink}`,
      background: bColors.ink
    }
  }, items.map((f, i) => React.createElement("div", {
    key: f.n,
    style: {
      background: bColors.bg,
      padding: '28px 26px 34px',
      position: 'relative',
      borderRight: viewport.isMobile ? 'none' : viewport.isTablet ? i % 2 === 0 ? `4px solid ${bColors.ink}` : 'none' : i % 3 !== 2 ? `4px solid ${bColors.ink}` : 'none',
      borderBottom: i < items.length - (viewport.isMobile ? 1 : viewport.isTablet ? 2 : 3) ? `4px solid ${bColors.ink}` : 'none',
      minHeight: 240
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      marginBottom: 24
    }
  }, React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontWeight: 700,
      fontSize: 12,
      letterSpacing: 2
    }
  }, "NO.", f.n), React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontWeight: 700,
      fontSize: 12,
      letterSpacing: 2,
      color: bColors.red
    }
  }, "\u25CF STABLE")), React.createElement("h3", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 34 : 42 : 54,
      margin: '0 0 14px',
      letterSpacing: -2,
      lineHeight: 1,
      color: bColors.ink
    }
  }, f.t), React.createElement("div", {
    style: {
      width: 60,
      height: 4,
      background: bColors.yellow,
      margin: '0 0 16px'
    }
  }), React.createElement("p", {
    style: {
      fontFamily: bBody,
      fontSize: 15,
      lineHeight: 1.5,
      color: bColors.ink,
      margin: 0,
      fontWeight: 500
    }
  }, f.d)))));
}
function BrutCommand({
  viewport
}) {
  return React.createElement("section", {
    style: {
      padding: sectionPadding(viewport),
      background: bColors.ink,
      color: bColors.bg,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      position: viewport.isMobile ? 'static' : 'absolute',
      top: 30,
      right: 56,
      transform: viewport.isMobile ? 'none' : 'rotate(4deg)',
      border: `3px solid ${bColors.yellow}`,
      padding: '10px 16px',
      color: bColors.yellow,
      fontFamily: bMono,
      fontSize: 11,
      letterSpacing: 2,
      fontWeight: 700,
      display: 'inline-block',
      marginBottom: viewport.isMobile ? 20 : 0
    }
  }, "\u25C9 LIVE TAPE \xB7 can0 @ 250K"), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 3,
      color: bColors.yellow,
      marginBottom: 16
    }
  }, "// EXHIBIT A \u2014 ONE PIPELINE, ONE TRUTH"), React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 42 : viewport.isCompactMobile ? 48 : 54 : viewport.isTablet ? 72 : 86,
      letterSpacing: viewport.isMobile ? -1.5 : -3,
      lineHeight: 0.95,
      margin: '0 0 40px',
      color: bColors.bg
    }
  }, "CAPTURE. DECODE.", React.createElement("br", null), React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "COMPARE."), " REPLAY."), React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : '1fr 1fr',
      gap: 24
    }
  }, React.createElement("div", {
    style: {
      background: bColors.bg,
      color: bColors.ink,
      padding: '24px 26px',
      border: `4px solid ${bColors.yellow}`
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 11,
      color: bColors.red,
      letterSpacing: 2,
      fontWeight: 700,
      marginBottom: 12
    }
  }, "# STEP 1 \u2014 CAPTURE + DECODE"), React.createElement("pre", {
    style: {
      margin: 0,
      fontFamily: bMono,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 11 : 12 : 14,
      lineHeight: 1.7,
      color: bColors.ink,
      overflowX: 'auto'
    }
  }, `$ canarchy capture can0 --jsonl \\
    | canarchy j1939 decode --stdin --jsonl

{"ts":"17:42:19.20","pgn":61444,
 "name":"EEC1","engine_rpm":1842.25}
{"ts":"17:42:19.22","pgn":61444,
 "name":"EEC1","engine_rpm":1847.00}
{"ts":"17:42:19.24","pgn":65262,
 "name":"ET1", "coolant_c":88}`)), React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '24px 26px',
      border: `4px solid ${bColors.bg}`
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 11,
      color: bColors.red,
      letterSpacing: 2,
      fontWeight: 700,
      marginBottom: 12
    }
  }, "# STEP 2 \u2014 COMPARE AGAINST BASELINE"), React.createElement("pre", {
    style: {
      margin: 0,
      fontFamily: bMono,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 11 : 12 : 14,
      lineHeight: 1.7,
      color: bColors.ink,
      overflowX: 'auto'
    }
  }, `$ canarchy j1939 compare \\
    baseline.candump run.candump \\
    --text

unique_pgns:
- run.candump: 65262[ET1]
dm1_differences:
- sa=0x00 [Engine #1]
  run.candump: present=True faults=spn=110/fmi=3
  baseline.candump: present=False faults=none`))));
}
function BrutMCP({
  viewport
}) {
  const tools = [{
    name: 'capture',
    args: 'interface, duration, decode',
    ret: 'stream<Event>'
  }, {
    name: 'decode',
    args: 'file, dbc?',
    ret: 'stream<Event>'
  }, {
    name: 'filter',
    args: 'expression, file',
    ret: 'stream<Event>'
  }, {
    name: 'replay',
    args: 'file, rate, interface?',
    ret: 'stream<Event>'
  }, {
    name: 'j1939_dm1',
    args: 'file, source_address?',
    ret: 'stream<Event>'
  }, {
    name: 'uds_scan',
    args: 'interface?',
    ret: 'stream<Event>'
  }, {
    name: 'dbc_inspect',
    args: 'dbc, search?, layout?',
    ret: 'Bundle'
  }, {
    name: 'gateway',
    args: 'src, dst, ack_active',
    ret: 'stream<Event>'
  }, {
    name: 'simulate',
    args: 'profile, rate?, ack_active',
    ret: 'stream<Event>'
  }];
  const transcript = [{
    k: 'user',
    who: 'USER',
    t: 'Audit the truck on can0 for 10s and flag anything that looks like an unsolicited diagnostic session.'
  }, {
    k: 'thought',
    t: '↳ agent decides to capture, then filter for UDS traffic before deciding whether an active probe is warranted'
  }, {
    k: 'call',
    fn: 'capture',
    body: '{ "interface": "can0", "duration": 10, "decode": "j1939" }'
  }, {
    k: 'ret',
    body: '{"command":"capture","ok":true,"data":{...}} … 428 events'
  }, {
    k: 'call',
    fn: 'filter',
    body: '{ "expression": "name~=UDS.*", "file": "$last" }'
  }, {
    k: 'ret',
    body: '3 matching events — all sa=0x27'
  }, {
    k: 'asst',
    who: 'AGENT',
    t: 'Flagged 3 uds.session.request from sa=0x27. No active probe attempted over MCP — that requires `canarchy uds scan can0`, gated behind --ack-active and a typed YES.'
  }];
  return React.createElement("section", {
    style: {
      padding: sectionPadding(viewport),
      background: bColors.ink,
      color: bColors.bg,
      borderTop: `4px solid ${bColors.ink}`,
      borderBottom: `4px solid ${bColors.ink}`,
      position: 'relative',
      overflow: 'hidden'
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'end',
      flexWrap: 'wrap',
      gap: 20
    }
  }, React.createElement("div", null, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 3,
      color: bColors.yellow,
      fontWeight: 700,
      marginBottom: 14
    }
  }, "\u25A0 MCP SERVER \xB7 AGENTS GET A SEAT"), React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 40 : viewport.isCompactMobile ? 46 : 56 : viewport.isTablet ? 82 : 110,
      letterSpacing: viewport.isMobile ? -1.5 : -3.5,
      lineHeight: 0.88,
      margin: 0,
      color: bColors.bg
    }
  }, "PLUG CLAUDE", React.createElement("br", null), React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "STRAIGHT INTO"), React.createElement("br", null), "THE CAN BUS.")), React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '12px 18px',
      fontFamily: bMono,
      fontSize: viewport.isCompactMobile ? 10 : 11,
      fontWeight: 700,
      letterSpacing: 2,
      border: `4px solid ${bColors.bg}`,
      transform: viewport.isMobile ? 'none' : 'rotate(2deg)'
    }
  }, "ALL TOOLS \xB7 ONE SCHEMA \xB7 ZERO GLUE CODE")), React.createElement("div", {
    style: {
      marginTop: 40,
      background: bColors.yellow,
      color: bColors.ink,
      border: `4px solid ${bColors.bg}`,
      padding: '22px 26px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 24,
      flexWrap: 'wrap'
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 12 : viewport.isCompactMobile ? 13 : 15 : 22,
      fontWeight: 700,
      letterSpacing: -0.5,
      overflowWrap: 'anywhere'
    }
  }, React.createElement("span", {
    style: {
      color: bColors.red
    }
  }, "$"), " canarchy mcp serve"), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 11,
      letterSpacing: 2,
      fontWeight: 700
    }
  }, "ONE-SHOT WIRE-UP: canarchy mcp install --client claude-desktop")), React.createElement("div", {
    style: {
      marginTop: 40,
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : '1.15fr 1fr',
      gap: 24
    }
  }, React.createElement("div", {
    style: {
      background: bColors.bg,
      color: bColors.ink,
      border: `4px solid ${bColors.yellow}`,
      padding: 0
    }
  }, React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '12px 18px',
      fontFamily: bDisplay,
      fontSize: viewport.isCompactMobile ? 14 : 16,
      letterSpacing: 2,
      borderBottom: `4px solid ${bColors.ink}`,
      overflowWrap: 'anywhere'
    }
  }, "TOOL CATALOG \xB7 canarchy MCP (showing 9 of the full surface)"), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: viewport.isCompactMobile ? 12 : 13,
      lineHeight: 1.75
    }
  }, tools.map((t, i) => React.createElement("div", {
    key: t.name,
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : '1.3fr 1.6fr 1fr',
      gap: viewport.isMobile ? 4 : 12,
      padding: '10px 18px',
      background: i % 2 ? 'transparent' : 'rgba(11,11,11,0.04)',
      borderBottom: i < tools.length - 1 ? `1px dashed ${bColors.ink}` : 'none'
    }
  }, React.createElement("span", {
    style: {
      fontWeight: 700,
      color: bColors.ink,
      overflowWrap: 'anywhere'
    }
  }, t.name), React.createElement("span", {
    style: {
      color: bColors.mute,
      overflowWrap: 'anywhere'
    }
  }, t.args), React.createElement("span", {
    style: {
      color: bColors.red,
      fontWeight: 700,
      textAlign: viewport.isMobile ? 'left' : 'right',
      overflowWrap: 'anywhere'
    }
  }, t.ret)))), React.createElement("div", {
    style: {
      borderTop: `4px solid ${bColors.ink}`,
      padding: '12px 18px',
      fontFamily: bMono,
      fontSize: 11,
      color: bColors.ink,
      letterSpacing: 1,
      fontWeight: 700,
      display: 'flex',
      justifyContent: 'space-between',
      background: bColors.paper,
      flexDirection: viewport.isMobile ? 'column' : 'row',
      gap: 8
    }
  }, React.createElement("span", null, "\u25A0 ALL EVENTS: canarchy/v1"), React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, "\u25C6 GUARDS: PLANNED"), React.createElement("span", null, "\u25A0 STREAMING"))), React.createElement("div", {
    style: {
      background: bColors.bg,
      color: bColors.ink,
      border: `4px solid ${bColors.bg}`,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      background: bColors.red,
      color: bColors.bg,
      padding: '12px 18px',
      fontFamily: bDisplay,
      fontSize: viewport.isCompactMobile ? 14 : 16,
      letterSpacing: 2,
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: 8,
      overflowWrap: 'anywhere'
    }
  }, React.createElement("span", null, "AGENT TRANSCRIPT \xB7 LIVE"), React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontSize: viewport.isCompactMobile ? 10 : 11,
      fontWeight: 700
    }
  }, "claude \u2194 canarchy")), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: viewport.isCompactMobile ? 11 : 12.5,
      lineHeight: 1.7,
      padding: '18px 20px',
      overflowWrap: 'anywhere'
    }
  }, transcript.map((row, i) => {
    if (row.k === 'user') return React.createElement("div", {
      key: i,
      style: {
        marginBottom: 10
      }
    }, React.createElement("span", {
      style: {
        background: bColors.ink,
        color: bColors.yellow,
        padding: '2px 8px',
        fontWeight: 700,
        letterSpacing: 1,
        fontSize: 10
      }
    }, row.who), ' ', React.createElement("span", {
      style: {
        color: bColors.ink
      }
    }, row.t));
    if (row.k === 'thought') return React.createElement("div", {
      key: i,
      style: {
        color: bColors.mute,
        marginBottom: 8,
        fontStyle: 'italic'
      }
    }, row.t);
    if (row.k === 'call') return React.createElement("div", {
      key: i,
      style: {
        marginBottom: 8,
        display: 'grid',
        gap: 2
      }
    }, React.createElement("div", null, React.createElement("span", {
      style: {
        color: bColors.red,
        fontWeight: 700
      }
    }, "\u2192 call"), ' ', React.createElement("span", {
      style: {
        color: bColors.ink,
        fontWeight: 700,
        overflowWrap: 'anywhere'
      }
    }, row.fn)), React.createElement("div", {
      style: {
        color: bColors.mute,
        paddingLeft: viewport.isMobile ? 0 : 18,
        overflowWrap: 'anywhere'
      }
    }, row.body));
    if (row.k === 'ret') return React.createElement("div", {
      key: i,
      style: {
        marginBottom: 10,
        paddingLeft: viewport.isMobile ? 0 : 18,
        color: bColors.mute,
        overflowWrap: 'anywhere'
      }
    }, React.createElement("span", {
      style: {
        color: bColors.ink,
        fontWeight: 700
      }
    }, "\u2190"), " ", row.body);
    if (row.k === 'asst') return React.createElement("div", {
      key: i,
      style: {
        marginTop: 8
      }
    }, React.createElement("span", {
      style: {
        background: bColors.red,
        color: bColors.bg,
        padding: '2px 8px',
        fontWeight: 700,
        letterSpacing: 1,
        fontSize: 10
      }
    }, row.who), ' ', React.createElement("span", {
      style: {
        color: bColors.ink
      }
    }, row.t));
    return null;
  })))), React.createElement("div", {
    style: {
      marginTop: 32,
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
      gap: 0,
      border: `4px solid ${bColors.bg}`
    }
  }, [{
    h: 'DETERMINISTIC',
    d: 'Same inputs in, same JSONL out. Agents can loop without drift.'
  }, {
    h: 'STREAMING',
    d: 'Tools return event streams. No 10k-token blobs, no truncation.'
  }, {
    h: 'DRY-RUN BY DEFAULT',
    d: 'Active commands require explicit --ack-active plus a typed YES. Guard framework (speed / ignition / session, marked PLANNED in the MCP catalog above) is on the roadmap.'
  }].map((b, i) => React.createElement("div", {
    key: b.h,
    style: {
      background: i === 1 ? bColors.yellow : bColors.bg,
      color: bColors.ink,
      padding: '20px 22px',
      borderLeft: viewport.isMobile ? 'none' : i > 0 ? `4px solid ${bColors.bg}` : 'none',
      borderTop: viewport.isMobile && i > 0 ? `4px solid ${bColors.bg}` : 'none'
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bDisplay,
      fontSize: 22,
      letterSpacing: -0.5,
      marginBottom: 6,
      display: 'flex',
      alignItems: 'center',
      gap: 10
    }
  }, b.h, b.planned && React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontSize: 9,
      letterSpacing: 2,
      fontWeight: 700,
      background: bColors.ink,
      color: bColors.yellow,
      padding: '2px 6px'
    }
  }, "PLANNED")), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      lineHeight: 1.55,
      color: bColors.ink
    }
  }, b.d)))));
}
function BrutMatrix({
  viewport
}) {
  const tools = ['CANarchy', 'can-utils', 'python-can', 'cantools', 'SavvyCAN', 'Caring Caribou', 'TruckDevil'];
  const rows = [['CLI-first', [1, 1, 0, 1, 0, 1, 0]], ['JSONL events', [1, 0, 0, 0, 0, 0, 0]], ['Pipe composition', [1, 0, 0, 0, 0, 0, 0]], ['J1939 native', [1, 0, 0, 0, 0, 0, 1]], ['UDS workflows', [1, 0, 0, 0, 0, 1, 0]], ['DBC decode/encode', [1, 0, 0, 1, 1, 0, 0]], ['Provider-backed DBC', [1, 0, 0, 0, 0, 0, 0]], ['Agent / MCP', [1, 0, 0, 0, 0, 0, 0]]];
  const mobileTools = tools.map((tool, index) => ({
    tool,
    index
  }));
  return React.createElement("section", {
    style: {
      padding: sectionPadding(viewport),
      background: bColors.bg
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      marginBottom: 30,
      flexDirection: viewport.isMobile ? 'column' : 'row',
      gap: 16
    }
  }, React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 42 : viewport.isCompactMobile ? 48 : 56 : viewport.isTablet ? 72 : 86,
      letterSpacing: viewport.isMobile ? -1.5 : -3,
      lineHeight: 0.9,
      margin: 0,
      color: bColors.ink
    }
  }, "THE", React.createElement("br", null), "MATRIX."), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      color: bColors.mute,
      textAlign: 'right',
      letterSpacing: 1
    }
  }, "FIRST-CLASS ONLY \xB7 NO HALFWAY", React.createElement("br", null), "\u25A0 = shipped \xB7 \u25A1 = not a focus")), viewport.isMobile ? React.createElement("div", {
    style: {
      display: 'grid',
      gap: 16
    }
  }, rows.map(row => React.createElement("div", {
    key: row[0],
    style: {
      border: `4px solid ${bColors.ink}`,
      background: bColors.bg
    }
  }, React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '12px 16px',
      fontFamily: bDisplay,
      fontSize: viewport.isCompactMobile ? 18 : 20,
      letterSpacing: 1
    }
  }, row[0]), React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
      gap: 0,
      background: bColors.ink
    }
  }, mobileTools.map(({
    tool,
    index
  }) => React.createElement("div", {
    key: tool,
    style: {
      gridColumn: index === mobileTools.length - 1 && mobileTools.length % 2 === 1 ? '1 / -1' : 'auto',
      background: index === 0 && row[1][index] === 1 ? bColors.yellow : bColors.bg,
      color: bColors.ink,
      padding: viewport.isCompactMobile ? '10px 12px' : '12px 14px',
      borderRight: index === mobileTools.length - 1 && mobileTools.length % 2 === 1 ? 'none' : index % 2 === 0 ? `2px solid ${bColors.ink}` : 'none',
      borderBottom: index < mobileTools.length - 2 ? `2px solid ${bColors.ink}` : 'none',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      minHeight: viewport.isCompactMobile ? 68 : 74
    }
  }, React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontSize: viewport.isCompactMobile ? 10 : 11,
      lineHeight: 1.35,
      color: bColors.mute,
      overflowWrap: 'anywhere'
    }
  }, tool), React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, React.createElement("span", {
    style: {
      fontFamily: bDisplay,
      fontSize: 18,
      lineHeight: 1,
      color: bColors.ink
    }
  }, row[1][index] ? '■' : '□'), React.createElement("span", {
    style: {
      fontFamily: bMono,
      fontSize: 10,
      letterSpacing: 1,
      color: bColors.ink,
      fontWeight: 700
    }
  }, row[1][index] ? 'YES' : 'NO')))))))) : React.createElement("div", {
    style: {
      border: `4px solid ${bColors.ink}`,
      background: bColors.ink,
      overflowX: 'auto'
    }
  }, React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '2fr repeat(7, 1fr)',
      minWidth: 820
    }
  }, React.createElement("div", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: '14px 18px',
      fontFamily: bDisplay,
      fontSize: 14,
      letterSpacing: 2
    }
  }, "WORKFLOW"), tools.map((t, i) => React.createElement("div", {
    key: t,
    style: {
      background: i === 0 ? bColors.red : bColors.ink,
      color: i === 0 ? bColors.bg : bColors.bg,
      padding: '14px 10px',
      textAlign: 'center',
      fontFamily: bDisplay,
      fontSize: 13,
      letterSpacing: 1,
      borderLeft: `2px solid ${bColors.ink}`
    }
  }, t))), rows.map((r, ri) => React.createElement("div", {
    key: r[0],
    style: {
      display: 'grid',
      gridTemplateColumns: '2fr repeat(7, 1fr)',
      background: bColors.bg,
      borderTop: `2px solid ${bColors.ink}`,
      minWidth: 820
    }
  }, React.createElement("div", {
    style: {
      padding: '14px 18px',
      fontFamily: bBody,
      fontWeight: 700,
      fontSize: 15,
      color: bColors.ink
    }
  }, r[0]), r[1].map((v, ci) => React.createElement("div", {
    key: ci,
    style: {
      padding: '14px 10px',
      textAlign: 'center',
      background: ci === 0 && v === 1 ? bColors.yellow : bColors.bg,
      color: bColors.ink,
      fontFamily: bDisplay,
      fontSize: 22,
      letterSpacing: 1,
      borderLeft: `2px solid ${bColors.ink}`
    }
  }, v ? '■' : '·'))))));
}
function BrutManifesto({
  viewport
}) {
  const points = ['ONE RUNTIME, MANY DOORS', 'CAPTURE FIRST, ASK QUESTIONS LATER', 'J1939 IS NOT A PLUGIN', 'AGENTS DRIVE \u00b7 HUMANS RIDE', 'SCRIPT IT, DON\u2019T CLICK IT', 'PoC || GTFO'];
  return React.createElement("section", {
    style: {
      background: bColors.yellow,
      color: bColors.ink,
      padding: viewport.isMobile ? '56px 18px' : viewport.isTablet ? '68px 28px' : '80px 56px',
      borderTop: `4px solid ${bColors.ink}`,
      borderBottom: `4px solid ${bColors.ink}`,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 3,
      color: bColors.red,
      fontWeight: 700,
      marginBottom: 14
    }
  }, "\u25B2\u25B2\u25B2 MANIFESTO \u25B2\u25B2\u25B2"), React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 42 : viewport.isCompactMobile ? 48 : 58 : viewport.isTablet ? 84 : 120,
      lineHeight: 0.9,
      letterSpacing: viewport.isMobile ? -1.5 : -4,
      margin: '0 0 40px'
    }
  }, "SIX RULES.", React.createElement("br", null), "ONE EXCEPTION: YOU."), React.createElement("ol", {
    style: {
      listStyle: 'none',
      padding: 0,
      margin: 0,
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : 'repeat(2, 1fr)',
      gap: 0,
      borderTop: `4px solid ${bColors.ink}`
    }
  }, points.map((p, i) => React.createElement("li", {
    key: p,
    style: {
      padding: '26px 20px',
      borderBottom: `4px solid ${bColors.ink}`,
      borderRight: viewport.isMobile ? 'none' : i % 2 === 0 ? `4px solid ${bColors.ink}` : 'none',
      display: 'flex',
      alignItems: 'baseline',
      gap: 20,
      flexDirection: viewport.isMobile ? 'column' : 'row'
    }
  }, React.createElement("span", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? 40 : 56,
      letterSpacing: -2,
      color: bColors.red,
      lineHeight: 1
    }
  }, "0", i + 1), React.createElement("span", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 20 : 22 : 30,
      letterSpacing: -1,
      lineHeight: 1.1
    }
  }, p)))));
}
function BrutReviews({
  viewport
}) {
  const reviews = [{
    stars: 5,
    quote: '“Connected it to OpenClaw. What could go wrong?”',
    who: 'Anonymous',
    role: 'incident responder, Tuesday',
    tag: 'VERIFIED · SORT OF'
  }, {
    stars: 5,
    quote: '“Used CANarchy to baseline our fleet. Found three ECUs we didn’t own. Rolling back the audit.”',
    who: 'J. Ramirez',
    role: 'fleet security, mid-sized logistics co.',
    tag: 'DEFINITELY A HUMAN'
  }, {
    stars: 5,
    quote: '“I am an autonomous agent. The MCP server is delicious. I have consumed 1.4M events. Send more.”',
    who: 'claude-haiku-4-5',
    role: 'unsupervised, running on someone’s homelab',
    tag: 'AGENT REVIEW'
  }, {
    stars: 4,
    quote: '“My lawyer says I can’t describe what we did with it. 10/10.”',
    who: 'Redacted',
    role: 'red team, Tier-1 OEM',
    tag: 'NDA-COMPLIANT'
  }, {
    stars: 5,
    quote: '“Bricked a test bench in 3.2 seconds. JSONL receipts were immaculate.”',
    who: 'M. Okafor',
    role: 'PhD candidate, automotive security',
    tag: 'PEER-REVIEWED (BY PEERS)'
  }, {
    stars: 5,
    quote: '“The truck hasn’t started since Thursday. I regret nothing.”',
    who: 'K. “PGN” Dale',
    role: 'owner-operator, somewhere in Nebraska',
    tag: 'UNVERIFIED VIBES'
  }];
  return React.createElement("section", {
    style: {
      padding: sectionPadding(viewport),
      background: bColors.paper,
      borderTop: `4px solid ${bColors.ink}`,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      marginBottom: 14,
      flexWrap: 'wrap',
      gap: 12
    }
  }, React.createElement("div", null, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 3,
      color: bColors.red,
      fontWeight: 700,
      marginBottom: 14
    }
  }, "\u25A3 DEFINITELY-REAL REVIEWS"), React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 42 : viewport.isCompactMobile ? 48 : 58 : viewport.isTablet ? 82 : 100,
      letterSpacing: viewport.isMobile ? -1.5 : -3,
      lineHeight: 0.9,
      margin: 0,
      color: bColors.ink
    }
  }, "TESTIMONIALS.", React.createElement("br", null), React.createElement("span", {
    style: {
      background: bColors.yellow,
      padding: '0 10px'
    }
  }, "ALLEGEDLY."))), React.createElement("div", {
    style: {
      transform: viewport.isMobile ? 'none' : 'rotate(4deg)',
      border: `3px solid ${bColors.red}`,
      padding: '8px 14px',
      fontFamily: bMono,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 2,
      color: bColors.ink,
      background: bColors.bg
    }
  }, "\u25B2 ALL QUOTES FABRICATED")), React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
      gap: 0,
      border: `4px solid ${bColors.ink}`,
      background: bColors.ink,
      marginTop: 40
    }
  }, reviews.map((r, i) => React.createElement("div", {
    key: i,
    style: {
      background: i % 2 ? bColors.yellow : bColors.bg,
      padding: '26px 26px 30px',
      position: 'relative',
      minHeight: 280,
      borderRight: viewport.isMobile ? 'none' : viewport.isTablet ? i % 2 === 0 ? `4px solid ${bColors.ink}` : 'none' : i % 3 !== 2 ? `4px solid ${bColors.ink}` : 'none',
      borderBottom: i < reviews.length - (viewport.isMobile ? 1 : viewport.isTablet ? 2 : 3) ? `4px solid ${bColors.ink}` : 'none'
    }
  }, React.createElement("div", {
    style: {
      fontFamily: bDisplay,
      fontSize: 22,
      color: bColors.red,
      letterSpacing: 2,
      marginBottom: 16
    }
  }, '★'.repeat(r.stars), React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, '☆'.repeat(5 - r.stars))), React.createElement("p", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isCompactMobile ? 19 : 22,
      lineHeight: 1.15,
      letterSpacing: -0.5,
      margin: '0 0 22px',
      color: bColors.ink
    }
  }, r.quote), React.createElement("div", {
    style: {
      width: 40,
      height: 3,
      background: bColors.ink,
      marginBottom: 12
    }
  }), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      color: bColors.ink,
      fontWeight: 700,
      letterSpacing: 1
    }
  }, r.who), React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 11,
      color: bColors.mute,
      marginTop: 2
    }
  }, r.role), React.createElement("div", {
    style: {
      position: 'absolute',
      top: 18,
      right: 18,
      background: bColors.ink,
      color: bColors.yellow,
      fontFamily: bMono,
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: 2,
      padding: '3px 8px'
    }
  }, r.tag)))), React.createElement("div", {
    style: {
      marginTop: 18,
      fontFamily: bMono,
      fontSize: 11,
      color: bColors.mute,
      letterSpacing: 1,
      textAlign: 'right'
    }
  }, "* Any resemblance to real people, fleets, or incidents is entirely intentional and also fully deniable."));
}
function BrutInstall({
  viewport
}) {
  return React.createElement("section", {
    style: {
      padding: viewport.isMobile ? '56px 18px' : viewport.isTablet ? '68px 28px' : '80px 56px',
      background: bColors.bg,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : '1fr 1.3fr',
      gap: 48,
      alignItems: 'stretch'
    }
  }, React.createElement("div", null, React.createElement("div", {
    style: {
      fontFamily: bMono,
      fontSize: 12,
      letterSpacing: 3,
      color: bColors.red,
      fontWeight: 700
    }
  }, "\u25A3 INSTALL / RUN"), React.createElement("h2", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isNarrowMobile ? 42 : viewport.isCompactMobile ? 48 : 56 : viewport.isTablet ? 72 : 92,
      lineHeight: 0.9,
      letterSpacing: viewport.isMobile ? -1.5 : -3,
      margin: '16px 0 26px',
      color: bColors.ink
    }
  }, "THREE", React.createElement("br", null), "COMMANDS.", React.createElement("br", null), React.createElement("span", {
    style: {
      background: bColors.yellow,
      padding: '0 10px'
    }
  }, "ZERO"), " FLUFF."), React.createElement("p", {
    style: {
      fontFamily: bBody,
      fontSize: 17,
      lineHeight: 1.5,
      color: bColors.ink,
      maxWidth: 460,
      fontWeight: 500
    }
  }, "Plug in a USB CAN interface, point it at a log file, or spin up a virtual bus. You\u2019ll have your first JSONL event before your coffee is cold.")), React.createElement("div", {
    style: {
      background: bColors.ink,
      color: bColors.bg,
      padding: viewport.isMobile ? '24px 18px' : '30px 32px',
      border: `4px solid ${bColors.ink}`,
      position: 'relative'
    }
  }, React.createElement("div", {
    style: {
      position: 'absolute',
      top: -14,
      left: 24,
      background: bColors.red,
      color: bColors.bg,
      fontFamily: bMono,
      fontSize: 11,
      letterSpacing: 2,
      fontWeight: 700,
      padding: '4px 10px'
    }
  }, `$ ZSH · canarchy v${RELEASE_VERSION}`), React.createElement("pre", {
    style: {
      margin: 0,
      fontFamily: bMono,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 11 : 12 : 15,
      lineHeight: 1.9,
      color: bColors.bg,
      overflowX: 'auto'
    }
  }, React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, "# 1. install"), '\n', React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "\u279C"), " pip install canarchy", '\n\n', React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, "# 2. check your environment"), '\n', React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "\u279C"), " canarchy doctor --text", '\n\n', React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, "# 3. stream + decode J1939 events as JSONL"), '\n', React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "\u279C"), " canarchy capture can0 --jsonl | canarchy j1939 decode --stdin --jsonl", '\n\n', React.createElement("span", {
    style: {
      color: bColors.mute
    }
  }, "# 4. (optional) let an agent drive it"), '\n', React.createElement("span", {
    style: {
      color: bColors.yellow
    }
  }, "\u279C"), " canarchy mcp serve", '\n'))));
}
const footerLinks = {
  DOCS: [{
    label: 'Getting Started',
    href: siteBase + '/docs/getting_started'
  }, {
    label: 'Command Spec',
    href: siteBase + '/docs/command_spec'
  }, {
    label: 'Event Schema',
    href: siteBase + '/docs/event-schema'
  }, {
    label: 'Matrix',
    href: siteBase + '/docs/feature-matrix'
  }],
  GUIDE: [{
    label: 'Backends',
    href: siteBase + '/docs/backends'
  }, {
    label: 'J1939',
    href: siteBase + '/docs/tutorials/j1939_heavy_vehicle'
  }, {
    label: 'UDS',
    href: siteBase + '/docs/tutorials'
  }, {
    label: 'Tutorials',
    href: siteBase + '/docs/tutorials'
  }],
  DEV: [{
    label: 'Architecture',
    href: siteBase + '/docs/architecture'
  }, {
    label: 'Design',
    href: siteBase + '/docs/overview'
  }, {
    label: 'Release',
    href: siteBase + '/docs/release'
  }, {
    label: 'TUI',
    href: siteBase + '/docs/tui_plan'
  }],
  SOCIAL: [{
    label: 'GitHub',
    href: 'https://github.com/hexsecs/canarchy'
  }, {
    label: 'Issues',
    href: 'https://github.com/hexsecs/canarchy/issues'
  }, {
    label: 'Discussions',
    href: 'https://github.com/hexsecs/canarchy/discussions'
  }, {
    label: 'Agents',
    href: siteBase + '/docs/agents'
  }]
};
function BrutFooter({
  viewport
}) {
  return React.createElement(React.Fragment, null, React.createElement(CautionStripe, {
    h: 14,
    flip: true
  }), React.createElement("footer", {
    style: {
      background: bColors.ink,
      color: bColors.bg,
      padding: viewport.isMobile ? '42px 18px 32px' : viewport.isTablet ? '50px 28px 36px' : '50px 56px 40px',
      fontFamily: bBody
    }
  }, React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: viewport.isMobile ? '1fr' : viewport.isTablet ? 'repeat(2, 1fr)' : '2fr 1fr 1fr 1fr 1fr',
      gap: 40
    }
  }, React.createElement("div", null, React.createElement("div", {
    style: {
      fontFamily: bDisplay,
      fontSize: viewport.isMobile ? viewport.isCompactMobile ? 34 : 40 : 44,
      letterSpacing: -1.5,
      color: bColors.yellow,
      lineHeight: 1
    }
  }, "CAN/ARCHY"), React.createElement("div", {
    style: {
      marginTop: 14,
      fontFamily: bMono,
      fontSize: 12,
      lineHeight: 1.7,
      color: '#d8d3c5'
    }
  }, "STREAM-FIRST CAN ANALYSIS RUNTIME.", React.createElement("br", null), "OPEN SOURCE \xB7 GPL-3.0 \xB7 BUILT BY hexsecs.", React.createElement("br", null), "FOR RESEARCHERS, NOT DEALERSHIPS.")), Object.entries(footerLinks).map(([h, links]) => React.createElement("div", {
    key: h
  }, React.createElement("div", {
    style: {
      fontFamily: bDisplay,
      fontSize: 14,
      letterSpacing: 2,
      color: bColors.yellow,
      marginBottom: 14
    }
  }, h), links.map(l => React.createElement("a", {
    key: l.label,
    href: l.href,
    target: l.href.startsWith('http') ? '_blank' : undefined,
    rel: l.href.startsWith('http') ? 'noopener noreferrer' : undefined,
    style: {
      display: 'block',
      fontFamily: bMono,
      fontSize: 12,
      marginBottom: 7,
      color: '#d8d3c5',
      textDecoration: 'none'
    }
  }, l.label))))), React.createElement("div", {
    style: {
      marginTop: 50,
      paddingTop: 20,
      borderTop: `2px solid ${bColors.yellow}`,
      display: 'flex',
      justifyContent: 'space-between',
      fontFamily: bMono,
      fontSize: 11,
      letterSpacing: 2,
      color: '#b0ab9e',
      flexDirection: viewport.isMobile ? 'column' : 'row',
      gap: 10
    }
  }, React.createElement("span", null, "HEXSECS / CANARCHY \xB7 GPL-3.0 \xB7 2026"), React.createElement("span", null, "TRY BUS STUFF \xB7 RECORD EVERYTHING"))));
}
function SiteBrutalist() {
  const viewport = useViewport();
  return React.createElement("div", {
    style: {
      width: '100%',
      height: '100%',
      background: bColors.bg,
      color: bColors.ink,
      fontFamily: bBody,
      position: 'relative',
      overflowX: 'hidden'
    }
  }, React.createElement(BrutNav, {
    viewport: viewport
  }), React.createElement(BrutHero, {
    viewport: viewport
  }), React.createElement(BrutTicker, {
    viewport: viewport
  }), React.createElement(BrutFeatures, {
    viewport: viewport
  }), React.createElement(BrutCommand, {
    viewport: viewport
  }), React.createElement(BrutMCP, {
    viewport: viewport
  }), React.createElement(BrutMatrix, {
    viewport: viewport
  }), React.createElement(BrutReviews, {
    viewport: viewport
  }), React.createElement(BrutManifesto, {
    viewport: viewport
  }), React.createElement(BrutInstall, {
    viewport: viewport
  }), React.createElement(BrutFooter, {
    viewport: viewport
  }));
}
window.SiteBrutalist = SiteBrutalist;