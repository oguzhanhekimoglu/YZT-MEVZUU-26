import { TestOperatorDataSource } from "./test-data-source";

describe("TestOperatorDataSource", () => {
  it("temel oturum verisini döndürür", async () => {
    const dataSource = new TestOperatorDataSource();

    await expect(dataSource.getSession()).resolves.toMatchObject({
      id: "fixture-idle-session",
      status: "idle",
      connection: "connected",
      localMode: true,
      targets: [],
      events: [],
    });
  });

  it("oturum komutlarında mevcut sonuçları korur ve durum yayınlar", async () => {
    const dataSource = new TestOperatorDataSource();
    await dataSource.selectVideo({ name: "gorev.mp4" });
    await expect(dataSource.start()).resolves.toMatchObject({ status: "preparing", sourceName: "gorev.mp4" });
    dataSource.advance();
    await expect(dataSource.pause()).resolves.toMatchObject({ status: "paused", targets: expect.any(Array) });
    await expect(dataSource.resume()).resolves.toMatchObject({ status: "running" });
    await expect(dataSource.stop()).resolves.toMatchObject({ status: "stopped", sourceName: "gorev.mp4" });
    dataSource.dispose();
  });

  it("test zamanını seçilen videonun gerçek süresinde sınırlar", async () => {
    const dataSource = new TestOperatorDataSource();
    await dataSource.selectVideo({ name: "kisa.mp4", durationSeconds: 20 });
    await dataSource.start();
    for (let index = 0; index < 10; index += 1) dataSource.advance();
    const session = await dataSource.getSession();
    expect(session).toMatchObject({ currentSeconds: 20, durationSeconds: 20, progress: 1 });
    expect(Math.max(...session.events.map((event) => event.timeSeconds))).toBeLessThanOrEqual(20);
    dataSource.dispose();
  });
});
