import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const token = "e2e-key-local-fake-more-than-thirty-two-characters";

test("du premier démarrage aux réserves, puis affichage mobile", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Ouvrir mes réserves" }).click();
  await expect(
    page.getByRole("heading", { name: "Connectez votre banque" }),
  ).toBeVisible();
  await expect(
    page.getByText("Configuration nécessaire sur le serveur"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Continuer avec des relevés CSV" })
    .click();
  await page
    .getByLabel("Nom du compte", { exact: true })
    .fill("Réserves familiales");
  await page.getByRole("button", { name: "Utiliser ce compte" }).click();
  const date = new Date();
  date.setDate(date.getDate() - 3);
  await page
    .getByLabel("Date du solde initial (fin de journée)")
    .fill(date.toISOString().slice(0, 10));
  await page.getByLabel("Solde à la fin de cette journée (€)").fill("1000,00");
  await page.getByLabel("Montant initial pour Vacances").fill("800,00");
  await page.getByLabel("Montant initial pour Sécurité").fill("200,00");
  await page
    .getByLabel("Je confirme le solde à la fin de la journée choisie.")
    .check();
  await page.getByRole("button", { name: "Vérifier la répartition" }).click();
  await page
    .getByLabel("Je confirme le compte, la date et la répartition ci-dessus.")
    .check();
  await page.getByRole("button", { name: "Créer le suivi" }).click();
  await expect(
    page.getByRole("heading", { name: "Enveloppes", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Total des enveloppes, non affecté inclus = solde du compte",
      { exact: true },
    ),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Importer un relevé CSV", exact: true })
    .click();
  const day = new Date();
  day.setDate(day.getDate() - 1);
  const csv = `booking_date;amount;raw_label;provider_transaction_id\n${day.toISOString().slice(0, 10)};115,01;VIR RES-VAC;e2e-1\n${day.toISOString().slice(0, 10)};20,00;INTERETS COMPTE DE RESERVE;e2e-2\n`;
  await page.getByLabel("Relevé CSV", { exact: true }).setInputFiles({
    name: "releve.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await page
    .getByLabel("Solde bancaire après ces opérations (€)")
    .fill("1135,01");
  await page
    .getByRole("button", { name: "Importer le relevé", exact: true })
    .click();
  await expect(page.getByText("Import terminé", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Fermer", exact: true }).click();

  await page
    .getByRole("button", { name: "Affecter les opérations", exact: true })
    .click();
  await expect(
    page.getByText("INTERETS COMPTE DE RESERVE", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Affecter", exact: true }).click();
  await page.getByLabel("Affecter à").selectOption({ label: "Sécurité" });
  await page.getByRole("button", { name: "Valider l’affectation" }).click();
  await expect(
    page.getByRole("heading", { name: "Tout est à sa place" }),
  ).toBeVisible();

  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Enveloppes", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Déplacer entre enveloppes", exact: true })
    .click();
  await page
    .getByLabel("Depuis", { exact: true })
    .selectOption({ label: "Vacances" });
  await page
    .getByLabel("Vers", { exact: true })
    .selectOption({ label: "Sécurité" });
  await page.getByLabel("Montant (€)", { exact: true }).fill("99999");
  await page.getByRole("button", { name: "Confirmer le déplacement" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "dépasse le solde disponible",
  );
  await page.getByLabel("Montant (€)", { exact: true }).fill("100,01");
  await page.getByRole("button", { name: "Confirmer le déplacement" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText(
      "Total des enveloppes, non affecté inclus = solde du compte",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.locator("tr").filter({ hasText: "Sécurité" }),
  ).toContainText("320,01");
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Enveloppes", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Vacances", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Au fil de l’année" }),
  ).toBeVisible();
  await page
    .getByLabel("Année", { exact: true })
    .selectOption(String(new Date().getFullYear() - 1));
  await expect(
    page.getByText("Aucune donnée sur cette année.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Enveloppes", exact: true })
    .click();

  await page
    .getByRole("button", { name: "Créer une enveloppe", exact: true })
    .click();
  await page.getByLabel("Nom de l’enveloppe").fill("Cadeaux");
  await page.getByLabel("Code bancaire").fill("RES-CADEAU");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Créer l’enveloppe", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Cadeaux", exact: true }).click();
  await page.getByRole("button", { name: "Modifier", exact: true }).click();
  await page.getByLabel("Nom de l’enveloppe").fill("Cadeaux annuels");
  await page
    .getByRole("button", { name: "Enregistrer les modifications" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Cadeaux annuels", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Archiver", exact: true }).click();
  await page.getByRole("button", { name: "Confirmer l’archivage" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Toutes les enveloppes" }).click();
  await page.getByRole("button", { name: "Archives", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Cadeaux annuels", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Actives", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page
      .getByRole("navigation")
      .getByRole("button", { name: "Enveloppes", exact: true }),
  ).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 320, height: 844 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 320);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Opérations" })
    .click();
  await page.getByLabel("Type", { exact: true }).selectOption("REALLOCATION");
  await page.getByRole("button", { name: "Filtrer", exact: true }).click();
  await expect(page.getByText("2 écriture(s)", { exact: true })).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);

  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Réglages" })
    .click();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter en JSON" }).click();
  expect((await downloadEvent).suggestedFilename()).toBe("lootsplit.json");
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page.getByLabel("Clé d’accès")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Clé d’accès")).toBeVisible();
  expect(errors).toEqual([]);
});

test("connexion bancaire et planification avec réponses simulées", async ({
  page,
}) => {
  let connected = false;
  let enabled = false;
  let hours = 6;
  let success: string | null = null;
  let failed = false;
  const status = () => ({
    configured: true,
    credentials_configured: true,
    module_installed: true,
    connected,
    masked_iban: connected ? "•••• 4321" : null,
    running: false,
    auto_sync_enabled: enabled,
    interval_hours: hours,
    last_success_at: success,
    last_attempt_at: success,
    next_sync_at: null,
    error_code: failed ? "action_required" : null,
    error: failed
      ? "La banque demande une validation dans son application."
      : null,
    automatic_paused: failed,
  });
  await page.route("**/api/banking/status", (route) =>
    route.fulfill({ json: status() }),
  );
  await page.route("**/api/banking/accounts", (route) =>
    route.fulfill({
      json: [
        {
          choice_id: "livret-a-choice",
          name: "Livret A",
          masked_iban: "•••• 1234",
          balance_cents: 500000,
        },
        {
          choice_id: "opaque-choice",
          name: "LEP",
          masked_iban: "•••• 4321",
          balance_cents: 113501,
        },
      ],
    }),
  );
  await page.route("**/api/banking/selection", (route) => {
    expect(route.request().postDataJSON()).toEqual({
      choice_id: "opaque-choice",
      confirmed: true,
    });
    connected = true;
    return route.fulfill({ json: status() });
  });
  await page.route("**/api/banking/schedule", (route) => {
    const body = route.request().postDataJSON();
    enabled = body.enabled;
    hours = body.interval_hours;
    return route.fulfill({ json: status() });
  });
  await page.route("**/api/sync", (route) => {
    if (success) {
      failed = true;
      return route.fulfill({
        status: 409,
        json: {
          detail: "La banque demande une validation dans son application.",
        },
      });
    }
    success = new Date().toISOString();
    return route.fulfill({ json: { imported: 0, duplicates: 2 } });
  });
  const headers = { Authorization: `Bearer ${token}` };
  const accounts = await page.request.get("/api/accounts", { headers });
  if (!(await accounts.json()).length) {
    const date = new Date();
    date.setDate(date.getDate() - 3);
    await page.request.post("/api/setup", {
      headers,
      data: {
        name: "LEP",
        activation_date: date.toISOString().slice(0, 10),
        opening_balance_cents: 0,
        allocations: {},
      },
    });
  }
  await page.route("**/api/accounts", async (route) => {
    const response = await route.fetch();
    const accounts = await response.json();
    return route.fulfill({
      response,
      json: accounts.map((account: { name: string }) => ({
        ...account,
        name: connected ? "LEP" : "Livret A",
      })),
    });
  });
  await page.goto("/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Ouvrir mes réserves" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Banque", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Banque", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Charger mes comptes" }).click();
  await page
    .getByLabel("Compte de réserve à suivre", { exact: true })
    .selectOption("opaque-choice");
  await page
    .getByLabel("Je confirme qu’il s’agit du compte de réserve déjà suivi ici.")
    .check();
  await page.getByRole("button", { name: "Associer ce compte" }).click();
  await expect(page.getByText("Compte de réserve associé")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Banque", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Synchroniser maintenant", exact: true })
    .click();
  await expect(
    page.getByText("0 opération(s) importée(s), 2 déjà connue(s).", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel("Activer la synchronisation automatique").check();
  await page.getByLabel("Fréquence", { exact: true }).selectOption("12");
  await page.getByRole("button", { name: "Enregistrer la fréquence" }).click();
  await expect(
    page.getByText("Fréquence de synchronisation enregistrée.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(enabled).toBe(true);
  expect(hours).toBe(12);
  await page
    .getByRole("button", { name: "Synchroniser maintenant", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "La banque demande une validation",
  );
  await expect(
    page.getByText("Les synchronisations automatiques sont suspendues", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/banking-settings.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Enveloppes", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Actualiser", exact: true }),
  ).toBeVisible();
});

test("sauvegarde manuelle, téléchargement et conservation après rechargement", async ({
  page,
}) => {
  const headers = { Authorization: `Bearer ${token}` };
  const accounts = await page.request.get("/api/accounts", { headers });
  if (!(await accounts.json()).length) {
    await page.request.post("/api/setup", {
      headers,
      data: {
        activation_date: new Date().toISOString().slice(0, 10),
        opening_balance_cents: 0,
        allocations: {},
      },
    });
  }
  await page.goto("/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Ouvrir mes réserves" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Réglages", exact: true })
    .click();
  await page.getByRole("button", { name: "Sauvegarder maintenant" }).click();
  await expect(
    page.getByText("Sauvegarde créée et vérifiée.", { exact: true }),
  ).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("link", { name: /Télécharger manuelle/ })
    .first()
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/^lootsplit-\d{8}T\d{12}Z\.db$/);
  const content = await readFile((await download.path())!);
  expect(content.subarray(0, 16).toString()).toBe("SQLite format 3\x00");
  await page.reload();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Réglages", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: /Télécharger manuelle/ }).first(),
  ).toBeVisible();
  await page
    .getByRole("heading", { name: "Sauvegardes", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/backups-settings.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
});
