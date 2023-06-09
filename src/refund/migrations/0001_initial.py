# Generated by Django 4.1.6 on 2023-04-06 14:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('order', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Refund',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('return_status', models.CharField(blank=True, max_length=255)),
                ('order', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='refunds', to='order.order')),
            ],
        ),
        migrations.CreateModel(
            name='RefundItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_modified', models.DateTimeField(auto_now=True, null=True)),
                ('return_date', models.DateTimeField()),
                ('transaction_updated', models.BooleanField(default=False, null=True)),
                ('sku', models.CharField(max_length=255)),
                ('asin', models.CharField(max_length=255)),
                ('fnsku', models.CharField(blank=True, default='', max_length=255)),
                ('product_name', models.CharField(max_length=255)),
                ('quantity', models.PositiveIntegerField(null=True)),
                ('fulfillment_center_id', models.CharField(blank=True, default='', max_length=255)),
                ('detailed_disposition', models.CharField(choices=[('CARRIER_DAMAGED', 'Carrier Damaged'), ('CUSTOMER_DAMAGED', 'Customer Damaged'), ('DAMAGED', 'Damaged'), ('DEFECTIVE', 'Defective'), ('SELLABLE', 'Sellable'), ('EXPIRED', 'Expired')], max_length=19)),
                ('reason', models.CharField(choices=[('OTHER', 'Return option not available'), ('ORDERED_WRONG_ITEM', 'I accidentally ordered the wrong item'), ('FOUND_BETTER_PRICE', 'I found better prices elsewhere'), ('NO_REASON_GIVEN', "No reason--I just don't want the product any more"), ('QUALITY_UNACCEPTABLE', 'Product performance/quality is not up to my expectations'), ('NOT_COMPATIBLE', 'Product is not compatible with my existing system'), ('DAMAGED_BY_FC', 'Product became damaged/defective after arrival'), ('MISSED_ESTIMATED_DELIVERY', "Item took too long to arrive; I don't want it any more"), ('MISSING_PARTS', 'Shipment was missing items or accessories'), ('DAMAGED_BY_CARRIER', 'Product was damaged/defective on arrival'), ('SWITCHEROO', 'Amazon sent me the wrong item'), ('DEFECTIVE', 'Item is defective'), ('EXTRA_ITEM', 'Extra item included in shipment'), ('UNWANTED_ITEM', 'Unwanted Item'), ('WARRANTY', 'Item defective after arrival -- Warranty'), ('UNAUTHORIZED_PURCHASE', 'Unauthorized purchase -- i.e. fraud'), ('UNDELIVERABLE_INSUFFICIENT_ADDRESS', 'Undeliverable; Insufficient address'), ('UNDELIVERABLE_FAILED_DELIVERY_ATTEMPTS', 'Undeliverable; Failed delivery attempts'), ('UNDELIVERABLE_REFUSED', 'Undeliverable; Refused'), ('UNDELIVERABLE_UNKNOWN', 'Undeliverable; Unknown'), ('UNDELIVERABLE_UNCLAIMED', 'Undeliverable; Unclaimed'), ('APPAREL_TOO_SMALL', 'Apparel; Product was too small'), ('APPAREL_TOO_LARGE', 'Apparel; Product was too large'), ('APPAREL_STYLE', 'Apparel; Did not like style of garment'), ('MISORDERED', 'Ordered wrong style/size/color'), ('NOT_AS_DESCRIBED', 'Not as described on website'), ('JEWELRY_TOO_SMALL', 'Jewelry; Too small/short'), ('JEWELRY_TOO_LARGE', 'Jewelry; Too large/long'), ('JEWELRY_BATTERY', 'Jewelry; Battery is dead'), ('JEWELRY_NO_DOCS', 'Jewelry; Missing manual/warranty'), ('JEWELRY_BAD_CLASP', 'Jewelry; Broken or malfunctioning clasp'), ('JEWELRY_LOOSE_STONE', 'Jewelry; Missing or loose stone'), ('JEWELRY_NO_CERT', 'Jewelry; Missing promised certification')], max_length=255)),
                ('lpn', models.CharField(blank=True, default=True, max_length=255)),
                ('status', models.CharField(max_length=255)),
                ('comment', models.TextField(blank=True)),
                ('order_item', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='refund_items', to='order.orderitem')),
                ('refund', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='refund_items', to='refund.refund')),
            ],
        ),
    ]
