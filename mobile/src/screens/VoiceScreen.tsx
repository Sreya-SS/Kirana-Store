import { useState } from 'react';
import {
  Alert as RNAlert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';

import { api, type ParsedLine } from '../api';
import { Button } from '../components';
import { colors } from '../theme';

type EditableLine = { item: string; quantity: string; unit: string };

export default function VoiceScreen() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  const [typedText, setTypedText] = useState('');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [lines, setLines] = useState<EditableLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toEditable = (parsed: ParsedLine[]): EditableLine[] =>
    parsed.map((p) => ({ item: p.item, quantity: String(p.quantity), unit: p.unit }));

  const startRecording = async () => {
    try {
      setError(null);
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setError('Microphone permission denied. You can type instead below.');
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e: any) {
      setError(e.message ?? 'Could not start recording. Try typing instead.');
    }
  };

  const stopAndTranscribe = async () => {
    try {
      setBusy(true);
      setError(null);
      setStatus('Transcribing… (first run loads the model, give it a few seconds)');
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error('No audio captured. Try again or type instead.');
      const res = await api.transcribeAudio(uri);
      setTranscript(res.transcript);
      setLines(toEditable(res.parsed));
      setStatus(res.parsed.length ? null : 'Nothing parsed — edit below or type instead.');
    } catch (e: any) {
      setError(e.message ?? 'Transcription failed. Try typing instead.');
      setStatus(null);
    } finally {
      setBusy(false);
    }
  };

  const parseTyped = async () => {
    if (!typedText.trim()) return;
    try {
      setBusy(true);
      setError(null);
      setStatus('Parsing…');
      const res = await api.transcribeText(typedText.trim());
      setTranscript(res.transcript);
      setLines(toEditable(res.parsed));
      setStatus(res.parsed.length ? null : 'Nothing parsed — try e.g. "10 kg rice, 5 packet biscuits".');
    } catch (e: any) {
      setError(e.message ?? 'Parsing failed.');
      setStatus(null);
    } finally {
      setBusy(false);
    }
  };

  const updateLine = (idx: number, field: keyof EditableLine, value: string) => {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  };
  const removeLine = (idx: number) => setLines((prev) => prev.filter((_, i) => i !== idx));

  const confirmSave = async () => {
    const payload = lines
      .map((l) => ({ item: l.item.trim(), quantity: parseFloat(l.quantity), unit: l.unit.trim() }))
      .filter((l) => l.item && !isNaN(l.quantity));
    if (!payload.length) {
      setError('Nothing to save. Add at least one valid row.');
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const res = await api.bulkUpsert(payload);
      RNAlert.alert(
        'Saved',
        `Updated ${res.updated.length} item(s), created ${res.created.length} new.`,
      );
      // Reset the flow.
      setTranscript(null);
      setLines([]);
      setTypedText('');
      setStatus('Saved! Check the Inventory tab.');
    } catch (e: any) {
      setError(e.message ?? 'Save failed.');
    } finally {
      setBusy(false);
    }
  };

  const isRecording = recorderState.isRecording;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <Text style={styles.h1}>Add stock by voice</Text>
        <Text style={styles.sub}>
          Say something like “10 kilo rice, 5 packet biscuits, 2 litre oil”. Nothing is saved until you
          review and confirm.
        </Text>

        <View style={styles.card}>
          <Button
            title={isRecording ? '⏹ Stop & transcribe' : '🎤 Start recording'}
            onPress={isRecording ? stopAndTranscribe : startRecording}
            variant={isRecording ? 'danger' : 'primary'}
            disabled={busy}
          />
          {isRecording && <Text style={styles.recording}>● Recording…</Text>}

          <Text style={styles.or}>— or type instead —</Text>
          <TextInput
            style={styles.input}
            placeholder='e.g. "10 kg rice, 5 packet biscuits"'
            value={typedText}
            onChangeText={setTypedText}
            multiline
          />
          <Button title="Parse text" onPress={parseTyped} variant="secondary" disabled={busy} />
        </View>

        {status && <Text style={styles.status}>{status}</Text>}
        {error && <Text style={styles.error}>⚠️ {error}</Text>}

        {transcript !== null && (
          <View style={styles.card}>
            <Text style={styles.h2}>Transcript</Text>
            <Text style={styles.transcript}>“{transcript}”</Text>

            <Text style={[styles.h2, { marginTop: 14 }]}>Review ({lines.length})</Text>
            {lines.length === 0 && <Text style={styles.sub}>No rows. Edit the text and parse again.</Text>}
            {lines.map((l, idx) => (
              <View key={idx} style={styles.row}>
                <TextInput
                  style={[styles.cell, { flex: 2 }]}
                  value={l.item}
                  onChangeText={(v) => updateLine(idx, 'item', v)}
                  placeholder="item"
                />
                <TextInput
                  style={[styles.cell, { flex: 1 }]}
                  value={l.quantity}
                  onChangeText={(v) => updateLine(idx, 'quantity', v)}
                  keyboardType="numeric"
                  placeholder="qty"
                />
                <TextInput
                  style={[styles.cell, { flex: 1 }]}
                  value={l.unit}
                  onChangeText={(v) => updateLine(idx, 'unit', v)}
                  placeholder="unit"
                />
                <Text style={styles.remove} onPress={() => removeLine(idx)}>
                  ✕
                </Text>
              </View>
            ))}

            {lines.length > 0 && (
              <View style={{ marginTop: 12 }}>
                <Button title={busy ? 'Saving…' : 'Confirm & save'} onPress={confirmSave} disabled={busy} />
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  h1: { fontSize: 20, fontWeight: '800', color: colors.text },
  h2: { fontSize: 15, fontWeight: '700', color: colors.text },
  sub: { color: colors.subtext, marginTop: 4, marginBottom: 12 },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.border, gap: 10 },
  or: { textAlign: 'center', color: colors.subtext, marginVertical: 4 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, fontSize: 15, backgroundColor: '#fff', minHeight: 44 },
  recording: { color: colors.danger, fontWeight: '700', textAlign: 'center' },
  status: { color: colors.primaryDark, marginBottom: 10 },
  error: { color: colors.danger, marginBottom: 10 },
  transcript: { fontStyle: 'italic', color: colors.text, marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 },
  cell: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 8, backgroundColor: '#fff' },
  remove: { color: colors.danger, fontSize: 18, paddingHorizontal: 6 },
});
