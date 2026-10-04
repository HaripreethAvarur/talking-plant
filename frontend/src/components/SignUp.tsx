import { useState } from "react";
import { api } from "../api";
import type { PlantRegistration, PlantType } from "../contracts";

const TYPES: { value: PlantType; emoji: string; label: string; hint: string }[] = [
  { value: "succulent", emoji: "🌵", label: "Succulent", hint: "cactus, aloe, jade" },
  { value: "plant", emoji: "🪴", label: "Houseplant", hint: "pothos, fern, flowers" },
  { value: "tree", emoji: "🌳", label: "Tree", hint: "bonsai, fig, citrus" },
];

/** First-launch form: who the kid is and which plant this is. No password. */
export function SignUp({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState<PlantRegistration>({
    username: "",
    plant_name: "",
    plant_type: "plant",
    location: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (field: keyof PlantRegistration) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

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
    <div className="overlay">
      <form className="card signup" onSubmit={submit}>
        <h2>Meet your plant! 🌱</h2>
        <label>
          Your name
          <input value={form.username} onChange={set("username")} placeholder="maya" required
            pattern="[A-Za-z0-9_.\-]{2,32}" title="2–32 letters or numbers, no spaces" autoFocus />
        </label>
        <label>
          Your plant's name
          <input value={form.plant_name} onChange={set("plant_name")} placeholder="Captain Leafy" required maxLength={40} />
        </label>
        <fieldset>
          <legend>What kind of plant?</legend>
          <div className="type-choices">
            {TYPES.map((type) => (
              <button type="button" key={type.value}
                className={`type-choice ${form.plant_type === type.value ? "type-chosen" : ""}`}
                onClick={() => setForm({ ...form, plant_type: type.value })}>
                <span aria-hidden>{type.emoji}</span>
                <strong>{type.label}</strong>
                <small>{type.hint}</small>
              </button>
            ))}
          </div>
        </fieldset>
        <label>
          ZIP code (for your local air)
          <input value={form.location} onChange={set("location")} placeholder="48105" required
            inputMode="numeric" pattern="\d{5}" title="5-digit US ZIP code" />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className="big-button" disabled={saving}>{saving ? "Saving…" : "Let's grow!"}</button>
      </form>
    </div>
  );
}
