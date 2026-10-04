import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { PlantGuess, PlantRegistration, PlantType } from "../contracts";
import { PlantCharacter } from "./PlantCharacter";

const TYPES: { value: PlantType; emoji: string; label: string; hint: string; color: string }[] = [
  { value: "succulent", emoji: "🌵", label: "Succulent", hint: "cactus, aloe", color: "bg-yellow" },
  { value: "plant", emoji: "🪴", label: "Houseplant", hint: "pothos, fern", color: "bg-green" },
  { value: "tree", emoji: "🌳", label: "Tree", hint: "bonsai, fig", color: "bg-blue" },
];

const BLANK: PlantRegistration = { username: "", plant_name: "", plant_type: "plant", location: "", species: "" };

/**
 * First launch: who you are, what your plant is called, and where it lives. The webcam
 * looks at the plant and fills in what it is (e.g. "Aloe vera", succulent); the child can
 * change it. With `initial`, the same form edits an existing plant (the username stays).
 */
export function SignUp({ onDone, initial, onCancel }: { onDone: () => void; initial?: PlantRegistration; onCancel?: () => void }) {
  const editing = !!initial;
  const [form, setForm] = useState<PlantRegistration>(initial ? { ...BLANK, ...initial, species: initial.species ?? "" } : BLANK);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [looking, setLooking] = useState(false);
  const [guess, setGuess] = useState<PlantGuess | null>(null);
  const touched = useRef({ species: false, type: false }); // never overwrite the child's own choice
  const set = (field: keyof PlantRegistration) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

  const identify = useCallback(async (force = false) => {
    setLooking(true);
    try {
      const found = await api<PlantGuess>("/api/plant/identify", { method: "POST" });
      setGuess(found);
      setForm((current) => ({
        ...current,
        species: force || !touched.current.species ? found.species : current.species,
        plant_type: force || !touched.current.type ? found.plant_type : current.plant_type,
      }));
      if (force) touched.current = { species: false, type: false };
    } catch {
      setGuess(null); // no camera or no plant in view: the child fills it in
    } finally {
      setLooking(false);
    }
  }, []);

  useEffect(() => {
    if (!editing) void identify();
  }, [editing, identify]);

  const useMyLocation = () => {
    if (!navigator.geolocation) return setError("This browser can't share its location. Type your ZIP code instead.");
    setLocating(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const { zip } = await api<{ zip: string }>(`/api/location/zip?lat=${coords.latitude}&lon=${coords.longitude}`);
          setForm((current) => ({ ...current, location: zip }));
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocating(false);
        setError("Location is turned off. Type your ZIP code instead.");
      },
      { timeout: 10000, maximumAge: 600000 },
    );
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api("/api/plant", { method: "POST", body: JSON.stringify({ ...form, species: form.species?.trim() || null }) });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="signup-page">
      <form className="card signup" onSubmit={submit}>
        <div className="signup-mascot">
          <PlantCharacter face="happy" speaking={false} level={0} />
        </div>
        <h2>{editing ? "Change my details ✏️" : "Hi! Let's be friends! 🌱"}</h2>

        <label className="field">
          <span>What's your name?</span>
          <input value={form.username} onChange={set("username")} placeholder="maya" required autoFocus={!editing}
            readOnly={editing} pattern="[A-Za-z0-9_.\-]{2,32}" title="2–32 letters or numbers, no spaces" />
        </label>

        <label className="field">
          <span>What will you call your plant?</span>
          <input value={form.plant_name} onChange={set("plant_name")} placeholder="Captain Leafy" required maxLength={40} />
        </label>

        <label className="field">
          <span>What plant is it?</span>
          <div className="zip-row">
            <input value={form.species ?? ""} placeholder={looking ? "Looking at your plant…" : "Aloe vera, fern, cactus…"}
              maxLength={60} onChange={(e) => { touched.current.species = true; setForm({ ...form, species: e.target.value }); }} />
            <button type="button" className="btn btn-blue" onClick={() => void identify(true)} disabled={looking}>
              {looking ? "Looking…" : "📸 Look again"}
            </button>
          </div>
          {guess && !looking && (
            <small className="identify-hint">📸 I think I'm {/^[aeiou]/i.test(guess.species) ? "an" : "a"} {guess.species}! Change it if I'm wrong.</small>
          )}
        </label>

        <fieldset className="field">
          <legend>What kind of plant is it?</legend>
          <div className="type-choices">
            {TYPES.map((type) => (
              <button type="button" key={type.value}
                className={`type-choice ${type.color} ${form.plant_type === type.value ? "type-chosen" : ""}`}
                aria-pressed={form.plant_type === type.value}
                onClick={() => { touched.current.type = true; setForm({ ...form, plant_type: type.value }); }}>
                <span className="type-emoji" aria-hidden>{type.emoji}</span>
                <strong>{type.label}</strong>
                <small>{type.hint}</small>
              </button>
            ))}
          </div>
        </fieldset>

        <label className="field">
          <span>Where do you live?</span>
          <div className="zip-row">
            <input value={form.location} onChange={set("location")} placeholder="ZIP code, like 48105" required
              inputMode="numeric" pattern="\d{5}" title="5-digit US ZIP code" />
            <button type="button" className="btn btn-blue" onClick={useMyLocation} disabled={locating}>
              {locating ? "Finding…" : "📍 Use my location"}
            </button>
          </div>
        </label>

        {error && <p className="form-error">{error}</p>}
        <button className="btn btn-green btn-big" disabled={saving}>
          {saving ? "Saving…" : editing ? "Save changes ✅" : "Let's grow! 🌱"}
        </button>
        {onCancel && <button type="button" className="btn btn-link" onClick={onCancel}>Never mind</button>}
      </form>
    </main>
  );
}
