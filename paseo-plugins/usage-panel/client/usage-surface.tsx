import { type PluginWorkspacePanelProps, useRpc } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Easing, Image, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { limitUsageRpc, type ProviderLimits } from "../shared/limits";
import { RECENT_DAYS, tokenUsageRpc, type ProviderTokens } from "../shared/usage";
import { callRpc } from "./fetch";
import { CODEX_LOGO, CLAUDE_LOGO } from "./provider-logos";
import { useAgentActivity } from "./use-agent-activity";
import {
  dateTimeText,
  limitNotice,
  numberText,
  parseTime,
  remainingPercent,
  resetText,
  sameLocalDay,
  timeText,
  tokenNotice,
  windowName,
  type Notice,
} from "./format";

const PROVIDERS = [
  { id: "codex", name: "Codex" },
  { id: "claude", name: "Claude" },
] as const;

// 패널을 열 때 한 번, 새로고침 버튼을 누를 때 한 번 읽는다. 주기적으로 다시 읽지 않는다.
const FETCH_ONCE = {
  staleTime: Infinity,
  refetchOnMount: "always",
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  retry: false,
} as const;

type MakeStyles = typeof makeStyles;
type Styles = ReturnType<MakeStyles>;
type Theme = PluginWorkspacePanelProps["theme"];

export function UsageSurface({ theme, layout }: PluginWorkspacePanelProps) {
  const running = useAgentActivity();
  const [reduceMotion, setReduceMotion] = useState(true);
  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then(
      (enabled) => {
        if (mounted) setReduceMotion(enabled);
      },
      () => {},
    );
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduceMotion);
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);
  const readLimits = useRpc(limitUsageRpc);
  const readTokens = useRpc(tokenUsageRpc);
  const limits = useQuery({
    queryKey: ["usage-panel", "limits"],
    queryFn: () => callRpc("usage.limits", () => readLimits({})),
    ...FETCH_ONCE,
  });
  const tokens = useQuery({
    queryKey: ["usage-panel", "tokens"],
    queryFn: () => callRpc("usage.tokens", () => readTokens({})),
    ...FETCH_ONCE,
  });
  const styles = useMemo(() => makeStyles(theme, layout.compact), [theme, layout.compact]);
  const busy = limits.isFetching || tokens.isFetching;
  const checkedAt = Math.max(limits.dataUpdatedAt, tokens.dataUpdatedAt);
  const nowMs = checkedAt || Date.now();

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.title}>사용량</Text>
          <Text style={styles.muted}>
            {busy ? "불러오는 중…" : checkedAt ? `마지막 확인 ${timeText(checkedAt)}` : ""}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="사용량 새로고침"
          disabled={busy}
          onPress={() => {
            void limits.refetch();
            void tokens.refetch();
          }}
          style={[styles.button, busy ? styles.buttonBusy : null]}
        >
          <Text style={styles.buttonText}>새로고침</Text>
        </Pressable>
      </View>

      <Text style={styles.sectionTitle}>남은 사용 한도</Text>
      <Text style={styles.muted}>계정 전체 기준입니다. 다른 PC에서 쓴 양도 함께 반영됩니다.</Text>
      {PROVIDERS.map((provider) => (
        <View key={provider.id} style={styles.card}>
          <LimitCard
            name={provider.name}
            providerId={provider.id}
            usage={limits.data?.[provider.id]}
            loading={limits.isPending}
            failed={limits.isError}
            nowMs={nowMs}
            styles={styles}
            theme={theme}
            running={running[provider.id]}
            reduceMotion={reduceMotion}
          />
        </View>
      ))}

      <Text style={styles.sectionTitle}>토큰 사용량 (이 PC에서 쓴 양)</Text>
      <Text style={styles.muted}>
        토큰은 AI가 읽고 쓴 글의 양을 세는 단위입니다. 이 PC에 남은 기록만 세므로 계정 전체 기준인 위
        한도와 맞지 않을 수 있습니다.
      </Text>
      {PROVIDERS.map((provider) => (
        <View key={provider.id} style={styles.card}>
          <TokenCard
            name={provider.name}
            tokens={tokens.data?.[provider.id]}
            loading={tokens.isPending}
            failed={tokens.isError}
            styles={styles}
          />
        </View>
      ))}
    </ScrollView>
  );
}

function LimitCard({
  name,
  providerId,
  usage,
  loading,
  failed,
  nowMs,
  styles,
  theme,
  running,
  reduceMotion,
}: {
  name: string;
  providerId: string;
  usage: ProviderLimits | null | undefined;
  loading: boolean;
  failed: boolean;
  nowMs: number;
  styles: Styles;
  theme: Theme;
  running: boolean;
  reduceMotion: boolean;
}) {
  const heading = (
    <View style={styles.cardHeading}>
      <ProviderLogo
        name={name}
        source={providerId === "codex" ? CODEX_LOGO : CLAUDE_LOGO}
        running={running}
        reduceMotion={reduceMotion}
        styles={styles}
      />
      <Text style={styles.cardHeadingText}>
        <Text style={styles.cardTitle}>{name}</Text>
        {usage?.planLabel ? <Text style={styles.muted}>{`  ${usage.planLabel}`}</Text> : null}
      </Text>
      {running ? <Text style={styles.runningText}>작업 중</Text> : null}
    </View>
  );
  if (loading) {
    return (
      <>
        {heading}
        <Text style={styles.muted}>불러오는 중…</Text>
      </>
    );
  }
  const notice = limitNotice(usage, failed);
  if (notice != null || usage == null) {
    return (
      <>
        {heading}
        <NoticeText notice={notice} styles={styles} />
      </>
    );
  }
  return (
    <>
      {heading}
      {usage.windows.map((limit) => {
        const remaining = remainingPercent(limit);
        const fill =
          limit.tone === "danger"
            ? theme.colors.statusDanger
            : limit.tone === "warning"
              ? theme.colors.statusWarning
              : theme.colors.accent;
        return (
          <View key={limit.id} style={styles.limitRow}>
            <View style={styles.rowBetween}>
              <Text style={styles.rowLabel}>{windowName(providerId, limit)}</Text>
              <Text style={styles.strong}>{remaining == null ? "알 수 없음" : `${Math.round(remaining)}% 남음`}</Text>
            </View>
            <View style={styles.track}>
              <View
                style={[
                  styles.fill,
                  { width: `${Math.min(100, Math.max(0, remaining ?? 0))}%`, backgroundColor: fill },
                ]}
              />
            </View>
            <Text style={styles.muted}>{resetText(limit, nowMs)}</Text>
          </View>
        );
      })}
    </>
  );
}

function ProviderLogo({
  name,
  source,
  running,
  reduceMotion,
  styles,
}: {
  name: string;
  source: string;
  running: boolean;
  reduceMotion: boolean;
  styles: Styles;
}) {
  const progress = useRef<Animated.Value | null>(null);
  if (progress.current == null) progress.current = new Animated.Value(0);
  const value = progress.current;

  useEffect(() => {
    if (!running || reduceMotion) {
      value.setValue(0);
      return;
    }
    const animation = Animated.loop(
      Animated.timing(value, {
        toValue: 1,
        duration: 2400,
        easing: Easing.out(Easing.quad),
        useNativeDriver: Platform.OS !== "web",
        isInteraction: false,
      }),
    );
    animation.start();
    return () => {
      animation.stop();
      value.setValue(0);
    };
  }, [running, reduceMotion, value]);

  return (
    <View style={styles.logoOuter}>
      {running && !reduceMotion ? (
        <Animated.View
          style={[
            styles.pulse,
            {
              opacity: value.interpolate({ inputRange: [0, 0.7, 1], outputRange: [0.6, 0.42, 0] }),
              transform: [{ scale: value.interpolate({ inputRange: [0, 1], outputRange: [1.08, 1.36] }) }],
            },
          ]}
        />
      ) : null}
      <View style={styles.logoBadge}>
        <Image source={{ uri: source }} style={styles.logoImage} accessibilityLabel={`${name} 로고`} />
      </View>
    </View>
  );
}

function TokenCard({
  name,
  tokens,
  loading,
  failed,
  styles,
}: {
  name: string;
  tokens: ProviderTokens | undefined;
  loading: boolean;
  failed: boolean;
  styles: Styles;
}) {
  const heading = <Text style={styles.cardTitle}>{name}</Text>;
  if (loading) {
    return (
      <>
        {heading}
        <Text style={styles.muted}>불러오는 중…</Text>
      </>
    );
  }
  const notice = tokenNotice(name, tokens, failed);
  if (notice != null || tokens?.status !== "ok") {
    return (
      <>
        {heading}
        <NoticeText notice={notice} styles={styles} />
      </>
    );
  }
  return (
    <>
      {heading}
      <View style={styles.rowBetween}>
        <Text style={styles.body}>오늘</Text>
        <Text style={styles.big}>{numberText(tokens.today.total)}</Text>
      </View>
      <Text style={styles.muted}>
        {`읽은 양 ${numberText(tokens.today.input)} · 쓴 양 ${numberText(tokens.today.output)}`}
      </Text>
      <Text style={styles.subTitle}>{`최근 ${RECENT_DAYS}일 대화별 사용량`}</Text>
      {tokens.sessions.length === 0 ? (
        <Text style={styles.muted}>{`최근 ${RECENT_DAYS}일 동안 쓴 기록이 없습니다.`}</Text>
      ) : (
        tokens.sessions.map((session) => (
          <View key={session.id} style={styles.sessionRow}>
            <Text style={styles.sessionTime}>{sessionTimeText(session.firstAt, session.lastAt)}</Text>
            <Text style={styles.sessionTotal}>{numberText(session.total)}</Text>
          </View>
        ))
      )}
    </>
  );
}

function NoticeText({ notice, styles }: { notice: Notice | null; styles: Styles }) {
  return notice ? <Text style={notice.tone === "danger" ? styles.danger : styles.muted}>{notice.text}</Text> : null;
}

function sessionTimeText(firstAt: string, lastAt: string): string {
  const firstMs = parseTime(firstAt) ?? 0;
  const lastMs = parseTime(lastAt) ?? 0;
  const end = sameLocalDay(firstMs, lastMs) ? timeText(lastMs) : dateTimeText(lastMs);
  return `${dateTimeText(firstMs)} ~ ${end}`;
}

function makeStyles(theme: Theme, compact: boolean) {
  const colors = theme.colors;
  return {
    screen: { flex: 1, backgroundColor: colors.surface0 },
    content: { padding: compact ? 16 : 24, gap: compact ? 10 : 12 },
    header: { flexDirection: "row" as const, alignItems: "center" as const, flexWrap: "wrap" as const, gap: 12 },
    headerText: { flexGrow: 1, flexShrink: 1, minWidth: 0, gap: 2 },
    title: { color: colors.foreground, fontSize: compact ? 20 : 24, fontWeight: "600" as const },
    sectionTitle: {
      color: colors.foreground,
      fontSize: compact ? 16 : 18,
      fontWeight: "600" as const,
      marginTop: compact ? 8 : 12,
    },
    subTitle: { color: colors.foreground, fontWeight: "600" as const, marginTop: 8 },
    card: {
      backgroundColor: colors.surface1,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 10,
      padding: compact ? 12 : 16,
      gap: 8,
    },
    cardTitle: { color: colors.foreground, fontSize: 16, fontWeight: "600" as const },
    cardHeading: { flexDirection: "row" as const, alignItems: "center" as const, gap: 8 },
    cardHeadingText: { flex: 1, flexShrink: 1, minWidth: 0 },
    runningText: { color: colors.accent, fontWeight: "600" as const, flexShrink: 0 },
    logoOuter: { width: 36, height: 36, alignItems: "center" as const, justifyContent: "center" as const },
    pulse: {
      position: "absolute" as const,
      width: 32,
      height: 32,
      borderRadius: 16,
      backgroundColor: colors.accent,
    },
    logoBadge: {
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: "center" as const,
      justifyContent: "center" as const,
      backgroundColor: colors.surface0,
      borderColor: colors.border,
      borderWidth: 1,
    },
    logoImage: { width: 24, height: 24, resizeMode: "contain" as const },
    limitRow: { gap: 4 },
    rowBetween: {
      flexDirection: "row" as const,
      justifyContent: "space-between" as const,
      alignItems: "center" as const,
      gap: 8,
    },
    rowLabel: { color: colors.foreground, flexShrink: 1, minWidth: 0 },
    sessionRow: {
      flexDirection: compact ? ("column" as const) : ("row" as const),
      justifyContent: "space-between" as const,
      alignItems: compact ? ("stretch" as const) : ("center" as const),
      gap: compact ? 2 : 8,
    },
    sessionTime: { color: colors.foregroundMuted, flexShrink: 1, minWidth: 0 },
    sessionTotal: {
      color: colors.foreground,
      alignSelf: compact ? ("flex-end" as const) : ("auto" as const),
    },
    track: { height: 8, borderRadius: 4, backgroundColor: colors.surface2, overflow: "hidden" as const },
    fill: { height: 8, borderRadius: 4 },
    body: { color: colors.foreground },
    strong: { color: colors.foreground, fontWeight: "600" as const, flexShrink: 0 },
    big: { color: colors.foreground, fontSize: compact ? 18 : 20, fontWeight: "600" as const },
    muted: { color: colors.foregroundMuted },
    danger: { color: colors.statusDanger },
    button: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.accent },
    buttonBusy: { opacity: 0.6 },
    buttonText: { color: colors.accentForeground },
  };
}
