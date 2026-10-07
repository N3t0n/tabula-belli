from django.core.management.base import BaseCommand
from django.conf import settings
from allauth.account.models import EmailAddress
from apps.players.models import Player
from cities_light.models import City


class Command(BaseCommand):
    help = 'Load test users for development'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete existing users first')

    @staticmethod
    def get_seed_users():
        return [
            {
                'username': 'rogal_dorn',
                'email': 'RogalDornVII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Rogal',
                'last_name': 'Dorn',
                'is_staff': False,
                'is_superuser': False,
                'location': (2562305, 'Valletta', 'MT')
            },
            {
                'username': 'lion_eljonson',
                'email': 'LionElJonsonI@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Lion',
                'last_name': "El'Jonson",
                'is_staff': False,
                'is_superuser': False,
                'location': (2510145, 'Trujillo', 'ES')
            },
            {
                'username': 'fulgrim',
                'email': 'FulgrimIII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Fulgrim',
                'last_name': 'Fulgrim',
                'is_staff': False,
                'is_superuser': False,
                'location': (3176959, 'Florence', 'IT')
            },
            {
                'username': 'perturabo',
                'email': 'PerturaboIV@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Perturabo',
                'last_name': 'Perturabo',
                'is_staff': False,
                'is_superuser': False,
                'location': (2928810, 'Essen', 'DE')
            },
            {
                'username': 'jaghatai_khan',
                'email': 'JaghataiKhanV@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Jaghatai',
                'last_name': 'Khan',
                'is_staff': False,
                'is_superuser': False,
                'location': (3054643, 'Budapest', 'HU')
            },
            {
                'username': 'leman_russ',
                'email': 'LemanRussVI@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Leman',
                'last_name': 'Russ',
                'is_staff': False,
                'is_superuser': False,
                'location': (3133895, 'Tromsø', 'NO')
            },
            {
                'username': 'konrad_curze',
                'email': 'KonradCurzeVIII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Konrad',
                'last_name': 'Curze',
                'is_staff': False,
                'is_superuser': False,
                'location': (683506, 'Bucharest', 'RO')
            },
            {
                'username': 'sanguinius',
                'email': 'SanguiniusIX@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Sanguinius',
                'last_name': 'Sanguinius',
                'is_staff': False,
                'is_superuser': False,
                'location': (3164603, 'Venice', 'IT')
            },
            {
                'username': 'ferrus_manus',
                'email': 'FerrusManusX@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Ferrus',
                'last_name': 'Manus',
                'is_staff': False,
                'is_superuser': False,
                'location': (2638077, 'Sheffield', 'GB')
            },
            {
                'username': 'angron',
                'email': 'AngronXII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Angron',
                'last_name': 'Angron',
                'is_staff': False,
                'is_superuser': False,
                'location': (3169070, 'Rome', 'IT')
            },
            {
                'username': 'roboute_guilliman',
                'email': 'RobouteGuillimanXIII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Roboute',
                'last_name': 'Guilliman',
                'is_staff': False,
                'is_superuser': False,
                'location': (2800866, 'Brussels', 'BE')
            },
            {
                'username': 'mortarion',
                'email': 'MortarionXIV@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Mortarion',
                'last_name': 'Mortarion',
                'is_staff': False,
                'is_superuser': False,
                'location': (2643123, 'Manchester', 'GB')
            },
            {
                'username': 'magnus_the_red',
                'email': 'MagnusTheRedXV@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Magnus',
                'last_name': 'The Red',
                'is_staff': False,
                'is_superuser': False,
                'location': (264371, 'Athens', 'GR')
            },
            {
                'username': 'horus_lupercal',
                'email': 'HorusLupercalXVI@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Horus',
                'last_name': 'Lupercal',
                'is_staff': False,
                'is_superuser': False,
                'location': (2761369, 'Vienna', 'AT')
            },
            {
                'username': 'lorgar_aurelian',
                'email': 'LorgarAurelianXVII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Lorgar',
                'last_name': 'Aurelian',
                'is_staff': False,
                'is_superuser': False,
                'location': (3109642, 'Santiago de Compostela', 'ES')
            },
            {
                'username': 'vulkan',
                'email': 'VulkanXVIII@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Vulkan',
                'last_name': 'Vulkan',
                'is_staff': False,
                'is_superuser': False,
                'location': (2525068, 'Catania', 'IT')
            },
            {
                'username': 'corvus_corax',
                'email': 'CorvusCoraxXIX@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Corvus',
                'last_name': 'Corax',
                'is_staff': False,
                'is_superuser': False,
                'location': (3096472, 'Katowice', 'PL')
            },
            {
                'username': 'alpharius',
                'email': 'AlphariusXX@mail.com',
                'password': 'TestPass123!',
                'first_name': 'Alpharius',
                'last_name': 'Alpharius',
                'is_staff': False,
                'is_superuser': False,
                'location': (2657896, 'Zürich', 'CH')
            },
        ]

    def handle(self, *args, **options):
        users = self.get_seed_users()

        if options['reset']:
            count = Player.objects.filter(
                username__in=[u['username'] for u in users]).delete()[0]
            if count:
                self.stdout.write(f"Deleted {count} users")

        created = 0
        skipped = 0

        for data in users:
            username = data['username']
            player_data = data.copy()
            password = player_data.pop('password')
            geoname_id, city_name, country_code = player_data.pop(
                'location'
            )

            city = City.objects.filter(
                geoname_id=geoname_id,
                country__code2=country_code
            ).select_related('country', 'region').first()

            if not city:
                self.stdout.write(self.style.WARNING(
                    f"City not found: {city_name}, {country_code} "
                    f"(GeoNames ID {geoname_id})"))
                continue

            player = Player.objects.filter(username=username).first()

            if player:
                skipped += 1
                location_fields = {
                    'country': city.country,
                    'region': city.region,
                    'city': city,
                }
                changed_fields = []
                for field, value in location_fields.items():
                    value_id = value.pk if value is not None else None
                    if getattr(player, f'{field}_id') != value_id:
                        setattr(player, field, value)
                        changed_fields.append(field)
                if changed_fields:
                    player.save(update_fields=changed_fields)
            else:
                player = Player.objects.create_user(
                    password=(
                        password
                        if username == settings.PUBLIC_DEMO_USERNAME
                        else None
                    ),
                    country=city.country,
                    region=city.region,
                    city=city,
                    **player_data
                )
                created += 1

            self._ensure_password_policy(player, password)
            self._ensure_email_address(player)

        self.stdout.write(f"Created {created}, skipped {skipped}")
        if created == 0 and skipped > 0:
            self.stdout.write("Use --reset to recreate")

    @staticmethod
    def _ensure_password_policy(player, seed_password):
        if player.username == settings.PUBLIC_DEMO_USERNAME:
            if not player.check_password(seed_password):
                player.set_password(seed_password)
                player.save(update_fields=['password'])
        elif player.has_usable_password():
            player.set_unusable_password()
            player.save(update_fields=['password'])

    @staticmethod
    def _ensure_email_address(player):
        normalized_email = player.email.lower()
        if player.email != normalized_email:
            player.email = normalized_email
            player.save(update_fields=['email'])

        email_address = EmailAddress.objects.filter(
            user=player,
            email__iexact=normalized_email,
        ).first()

        EmailAddress.objects.filter(
            user=player,
            primary=True,
        ).exclude(pk=getattr(email_address, 'pk', None)).update(primary=False)

        if email_address is None:
            email_address = EmailAddress(user=player)

        email_address.email = normalized_email
        email_address.primary = True
        email_address.verified = True
        email_address.save()
