# NestJS Core Evidence

```ts
@Controller('orders')
@UseGuards(AuthGuard)
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Get(':id')
  async getOne(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.orders.findOwnedBy(id, user.id); // service enforces ownership, not the controller
  }
}
```

Evidence: a `TestingModule` integration test for the module's wiring, a DTO invalid-input
test asserting the `ValidationPipe` rejects it, a guard test asserting an
unauthenticated/unauthorized request is rejected, and an error-response test asserting the
`ExceptionFilter` maps a thrown domain error to the right HTTP status without leaking
internals.
