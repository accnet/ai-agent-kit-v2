# NestJS Data Access Evidence

```ts
@Injectable()
export class OrdersRepository {
  constructor(private readonly manager: EntityManager) {}

  async createWithItems(order: NewOrder, items: NewOrderItem[]): Promise<Order> {
    return this.manager.transaction(async (tx) => {
      const saved = await tx.save(Order, order);
      await tx.save(OrderItem, items.map((i) => ({ ...i, orderId: saved.id })));
      return saved; // both writes commit or roll back together
    });
  }
}
```

Evidence: a migration up/down result run against a disposable database, a
transaction-rollback test (a forced failure mid-transaction leaves no partial write), an
authorization-scoped query test (a user cannot read another tenant's rows), and a
query-plan baseline for any new index.
