import { expect, test } from "@playwright/test";

test("démarrage bancaire : choix explicite, expiration et reprise sans perdre la répartition", async ({
  page,
}) => {
  let initialized = false;
  let discoveries = 0;
  let submissions = 0;
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const reconciliation = {
    bank_balance_cents: 100000,
    envelopes_total_cents: 100000,
    unassigned_cents: 10000,
    difference_cents: 0,
    reconciled: true,
    last_sync_at: null,
    last_sync_error: null,
  };
  const envelopes = [
    {
      id: 1,
      name: "Sécurité",
      code: "RES-SECU",
      description: "",
      icon: "",
      sort_order: 0,
      status: "ACTIVE",
      is_system: false,
      balance_cents: 80000,
    },
    {
      id: 2,
      name: "Vacances",
      code: "RES-VAC",
      description: "",
      icon: "",
      sort_order: 1,
      status: "ACTIVE",
      is_system: false,
      balance_cents: 10000,
    },
    {
      id: 3,
      name: "NON AFFECTÉ",
      code: null,
      description: "",
      icon: "",
      sort_order: 999,
      status: "ACTIVE",
      is_system: true,
      balance_cents: 10000,
    },
  ];
  await page.route("**/api/accounts", (route) =>
    route.fulfill({
      json: initialized
        ? [{ id: 1, name: "LEP", activation_date: "2026-01-01" }]
        : [],
    }),
  );
  await page.route(/\/api\/envelopes(?:\?.*)?$/, (route) =>
    route.fulfill({ json: initialized ? envelopes : [] }),
  );
  await page.route("**/api/dashboard", (route) =>
    route.fulfill({
      json: {
        reconciliation,
        envelopes,
        anomalies: {
          count: 0,
          unassigned_transaction_ids: [],
          negative_envelope_ids: [],
          suspected_duplicate_fingerprints: [],
          reconciliation,
        },
      },
    }),
  );
  await page.route("**/api/banking/status", (route) =>
    route.fulfill({
      json: {
        configured: true,
        credentials_configured: true,
        module_installed: true,
        connected: initialized,
        masked_iban: initialized ? "•••• 4321" : null,
        running: false,
        auto_sync_enabled: initialized,
        interval_hours: 6,
        next_sync_at: null,
        last_success_at: null,
        last_attempt_at: null,
        error_code: null,
        error: null,
        automatic_paused: false,
      },
    }),
  );
  await page.route("**/api/banking/accounts", (route) => {
    discoveries++;
    return route.fulfill({
      json: [
        {
          choice_id: `choice-${discoveries}`,
          name: "LEP",
          masked_iban: "•••• 4321",
          balance_cents: 150000,
        },
      ],
    });
  });
  await page.route("**/api/setup", (route) => {
    const body = route.request().postDataJSON();
    expect(body.name).toBe("LEP");
    expect(body.opening_balance_cents).toBe(100000);
    expect(body.bank_confirmed).toBe(true);
    expect(body.auto_sync_enabled).toBe(true);
    expect(
      body.envelopes.map((e: { amount_cents: number }) => e.amount_cents),
    ).toEqual([80000, 10000]);
    submissions++;
    if (submissions === 1)
      return route.fulfill({
        status: 409,
        json: {
          detail:
            "Le choix bancaire a expiré. Revenez à la connexion et rechargez les comptes.",
        },
      });
    expect(body.bank_choice_id).toBe("choice-2");
    initialized = true;
    return route.fulfill({ status: 201, json: reconciliation });
  });
  await page.goto("/");
  await page
    .getByLabel("Clé d’accès")
    .fill("e2e-key-local-fake-more-than-thirty-two-characters");
  await page.getByRole("button", { name: "Ouvrir mes réserves" }).click();
  await expect(
    page.getByRole("heading", { name: "Connectez votre banque" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Tester la connexion" }).click();
  await page.getByRole("button", { name: "Choisir le compte" }).click();
  await expect(page.locator('input[name="choice"]')).not.toBeChecked();
  await page.getByRole("radio").check();
  await page.getByRole("button", { name: "Utiliser ce compte" }).click();
  await expect(
    page.getByLabel("Solde à la fin de cette journée (€)"),
  ).toHaveValue("");
  await page.getByLabel("Solde à la fin de cette journée (€)").fill("1000");
  await page.getByLabel("Montant initial pour Sécurité").fill("1100");
  await page.getByLabel("Montant initial pour Vacances").fill("100");
  await page
    .getByLabel("Je confirme le solde à la fin de la journée choisie.")
    .check();
  await page.getByRole("button", { name: "Vérifier la répartition" }).click();
  await expect(page.getByRole("alert")).toContainText("dépasse");
  await page.getByLabel("Montant initial pour Sécurité").fill("800");
  await page.getByRole("button", { name: "Vérifier la répartition" }).click();
  await page
    .getByLabel("Activer l’actualisation automatique toutes les 6 heures")
    .check();
  await page
    .getByLabel("Je confirme le compte, la date et la répartition ci-dessus.")
    .check();
  await page.getByRole("button", { name: "Créer le suivi" }).click();
  await expect(page.getByRole("alert")).toContainText("expiré");
  await page
    .getByRole("button", { name: "Revenir à la connexion bancaire" })
    .click();
  await page.getByRole("button", { name: "Tester la connexion" }).click();
  await page.getByRole("button", { name: "Choisir le compte" }).click();
  await page.getByRole("radio").check();
  await page.getByRole("button", { name: "Utiliser ce compte" }).click();
  await expect(page.getByLabel("Montant initial pour Sécurité")).toHaveValue(
    "800",
  );
  await page
    .getByLabel("Je confirme le solde à la fin de la journée choisie.")
    .check();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page.screenshot({
    path: "test-results/onboarding-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Vérifier la répartition" }).click();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: "test-results/onboarding-confirm.png",
    fullPage: true,
  });
  await page
    .getByLabel("Je confirme le compte, la date et la répartition ci-dessus.")
    .check();
  await page.getByRole("button", { name: "Créer le suivi" }).click();
  await expect(
    page.getByRole("heading", { name: "Enveloppes", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Compte associé · premier import attendu"),
  ).toBeVisible();
  expect(submissions).toBe(2);
  expect(errors).toEqual([]);
});
