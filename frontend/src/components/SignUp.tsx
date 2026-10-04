import { useState } from "react";
import { api } from "../api";
import type { PlantRegistration, PlantType } from "../contracts";
import { PlantCharacter } from "./PlantCharacter";

const TYPES: { value: PlantType; emoji: string; label: string; hint: string; color: string }[] = [
  { value: "succulent", emoji: "🌵", label: "Succulent", hint: "cactus, aloe", color: "bg-yellow" },
  { value: "plant", emoji: "🪴", label: "Houseplant", hint: "pothos, fern", color: "bg-green" },
  { value: "tree", emoji: "🌳", label: "Tree", hint: "bonsai, fig", color: "bg-blue" },
];

/** First launch: who you are, what your plant is called, and where it lives. */
export function SignUp({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState<PlantRegistration>({ username: "", plant_name: "", plant_type: "plant", location: "" });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const set = (field: keyof PlantRegistration) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

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
      await api("/api/plant", { method: "POST", body: JSON.stringify(form) });
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
        <h2>Hi! Let's be friends! 🌱</h2>

        <label className="field">
          <span>What's your name?</span>
          <input value={form.username} onChange={set("username")} placeholder="maya" required autoFocus
            pattern="[A-Za-z0-9_.\-]{2,32}" title="2–32 letters or numbers, no spaces" />
        </label>

        <label className="field">
          <span>What will you call your plant?</span>
          <input value={form.plant_name} onChange={set("plant_name")} placeholder="Captain Leafy" required maxLength={40} />
        </label>

        <fieldset className="field">
          <legend>What kind of plant is it?</legend>
          <div className="type-choices">
            {TYPES.map((type) => (
              <button type="button" key={type.value}
                className={`type-choice ${type.color} ${form.plant_type === type.value ? "type-chosen" : ""}`}
                aria-pressed={form.plant_type === type.value}
                onClick={() => setForm({ ...form, plant_type: type.value })}>
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
        <button className="btn btn-green btn-big" disabled={saving}>{saving ? "Planting…" : "Let's grow! 🌱"}</button>
      </form>
    </main>
  );
}
