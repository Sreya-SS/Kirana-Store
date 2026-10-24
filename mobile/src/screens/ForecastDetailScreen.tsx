import { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import Svg, { G, Line, Rect, Text as SvgText } from 'react-native-svg';

import type { InventoryStackParams } from '../../App';
import { api, type ForecastResponse } from '../api';
import { Button, ErrorBox, Loading } from '../components';
import { colors } from '../theme';

type Props = NativeStackScreenProps<InventoryStackParams, 'ForecastDetail'>;

const CHART_W = 320;
const CHART_H = 180;
const PAD_L = 28;
const PAD_B = 22;

export default function ForecastDetailScreen({ route }: Props) {
  const { itemId } = route.params;
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stockInput, setStockInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const res = await api.getForecast(itemId);
      setData(res);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load forecast');
    } finally {
      setLoading(false);
    }
  }, [itemId]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const saveStock = async () => {
    const value = parseFloat(stockInput);
    if (isNaN(value) || value < 0) {
      setSaveMsg('Enter a valid non-negative number.');
      return;
    }
    try {
      setSaving(true);
      setSaveMsg(null);
      await api.updateStock(itemId, value);
      setSaveMsg(`Stock updated to ${value}.`);
      setStockInput('');
    } catch (e: any) {
      setSaveMsg(e.message ?? 'Update failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loading label="Forecasting…" />;
  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!data) return null;

  const m = data.metrics;
  const lgbmWins = m.wape_lightgbm <= m.wape_baseline;

  // Chart geometry
  const n = data.forecast.length;
  const maxVal = Math.max(
    1,
    ...data.forecast.map((p) => p.qty),
    ...data.baseline.map((p) => p.qty),
  );
  const plotW = CHART_W - PAD_L;
  const plotH = CHART_H - PAD_B;
  const groupW = plotW / n;
  const barW = groupW * 0.32;
  const y = (v: number) => plotH - (v / maxVal) * plotH;

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={{ padding: 16 }}>
      <Text style={styles.h1}>7-day demand forecast</Text>
      <Text style={styles.sub}>
        {data.item_name} · units in {data.unit}
      </Text>

      {/* Chart */}
      <View style={styles.card}>
        <Svg width={CHART_W} height={CHART_H}>
          {/* baseline axis line */}
          <Line x1={PAD_L} y1={plotH} x2={CHART_W} y2={plotH} stroke={colors.border} strokeWidth={1} />
          {/* y max label */}
          <SvgText x={0} y={12} fontSize={10} fill={colors.subtext}>
            {Math.round(maxVal)}
          </SvgText>
          <SvgText x={0} y={plotH} fontSize={10} fill={colors.subtext}>
            0
          </SvgText>
          {data.forecast.map((p, i) => {
            const gx = PAD_L + i * groupW + groupW / 2;
            const b = data.baseline[i];
            const day = p.date.slice(8, 10) + '/' + p.date.slice(5, 7);
            return (
              <G key={p.date}>
                {/* LightGBM bar */}
                <Rect x={gx - barW - 1} y={y(p.qty)} width={barW} height={plotH - y(p.qty)} fill={colors.good} rx={2} />
                {/* Baseline bar */}
                <Rect x={gx + 1} y={y(b.qty)} width={barW} height={plotH - y(b.qty)} fill={colors.baseline} rx={2} />
                <SvgText x={gx} y={CHART_H - 6} fontSize={8} fill={colors.subtext} textAnchor="middle">
                  {day}
                </SvgText>
              </G>
            );
          })}
        </Svg>
        <View style={styles.legendRow}>
          <Legend color={colors.good} label="LightGBM" />
          <Legend color={colors.baseline} label="Baseline (7-day avg)" />
        </View>
      </View>

      {/* WAPE comparison */}
      <View style={styles.card}>
        <Text style={styles.h2}>Model accuracy (backtest, last {m.backtest_days} days)</Text>
        <Text style={styles.metricNote}>WAPE — lower is better</Text>
        <View style={styles.metricRow}>
          <MetricPill label="Baseline" value={m.wape_baseline_pct} highlight={!lgbmWins} />
          <MetricPill label="LightGBM" value={m.wape_lightgbm_pct} highlight={lgbmWins} />
        </View>
        <Text style={styles.verdict}>
          {lgbmWins
            ? `LightGBM is better by ${(m.wape_baseline_pct - m.wape_lightgbm_pct).toFixed(1)} pts.`
            : `Baseline is better by ${(m.wape_lightgbm_pct - m.wape_baseline_pct).toFixed(1)} pts.`}
        </Text>
        <Text style={styles.synthetic}>{m.note}</Text>
      </View>

      {/* Quick stock update (uses PUT /items/{id}/stock) */}
      <View style={styles.card}>
        <Text style={styles.h2}>Update stock</Text>
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
          <TextInput
            style={styles.input}
            placeholder={`New stock (${data.unit})`}
            keyboardType="numeric"
            value={stockInput}
            onChangeText={setStockInput}
          />
          <Button title={saving ? 'Saving…' : 'Save'} onPress={saveStock} disabled={saving} />
        </View>
        {saveMsg && <Text style={styles.saveMsg}>{saveMsg}</Text>}
      </View>
    </ScrollView>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legend}>
      <View style={[styles.swatch, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

function MetricPill({ label, value, highlight }: { label: string; value: number; highlight: boolean }) {
  return (
    <View style={[styles.pill, highlight && styles.pillHi]}>
      <Text style={[styles.pillLabel, highlight && { color: '#fff' }]}>{label}</Text>
      <Text style={[styles.pillValue, highlight && { color: '#fff' }]}>{value}%</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  h1: { fontSize: 20, fontWeight: '800', color: colors.text },
  sub: { color: colors.subtext, marginTop: 2, marginBottom: 12 },
  h2: { fontSize: 15, fontWeight: '700', color: colors.text, marginBottom: 8 },
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    padding: 14,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.border,
  },
  legendRow: { flexDirection: 'row', gap: 18, marginTop: 8, justifyContent: 'center' },
  legend: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 12, height: 12, borderRadius: 3 },
  legendText: { fontSize: 12, color: colors.subtext },
  metricNote: { fontSize: 12, color: colors.subtext, marginBottom: 10 },
  metricRow: { flexDirection: 'row', gap: 12 },
  pill: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.border },
  pillHi: { backgroundColor: colors.primary, borderColor: colors.primary },
  pillLabel: { fontSize: 13, color: colors.subtext, fontWeight: '600' },
  pillValue: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: 2 },
  verdict: { marginTop: 10, fontWeight: '700', color: colors.primaryDark },
  synthetic: { marginTop: 8, fontSize: 11, color: colors.subtext, fontStyle: 'italic' },
  input: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, fontSize: 15, backgroundColor: '#fff' },
  saveMsg: { marginTop: 8, color: colors.primaryDark },
});
