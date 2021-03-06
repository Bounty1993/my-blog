from datetime import datetime, timedelta

from django import forms

from .models import Donation, Message, Room


class RoomRegisterForm(forms.ModelForm):
    date_expires = forms.DateField(
        input_formats=('%d/%m/%Y',), label='Data wygaśnięcia',
        help_text='Zbiórka nie może trwać więcej niż 183 dni')
    description = forms.CharField(widget=forms.Textarea, label='Opis')

    class Meta:
        model = Room
        fields = [
            'receiver',
            'gift',
            'gift_url',
            'price',
            'description',
            'to_collect',
            'visible',
            'date_expires'
        ]
        help_texts = {
            'receiver': 'Osoba która otrzyma zebrane środki.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['to_collect'].widget = forms.HiddenInput()
        self.fields['to_collect'].required = False

    def clean_date_expires(self):
        """method check if today <= expires_date < today + 183 days"""
        date_expires = self.cleaned_data['date_expires']
        today = datetime.now().date()
        half_year_later = today + timedelta(days=183)
        if date_expires > half_year_later:
            raise forms.ValidationError(
                'Data wygaśnięcia nie może byc późniejsza niż 183 dni'
            )
        if date_expires <= today:
            raise forms.ValidationError(
                'Data wygraśnięcia musi być w przyszłości'
            )
        return date_expires

    def clean(self):
        """
        to_collect has to be empty because latter it will be filled
        """
        cleaned_data = super().clean()
        to_collect = cleaned_data['to_collect']
        if to_collect:
            raise forms.ValidationError('Kwota do zebrania powinna być pusta')


class RoomUpdateForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            'receiver',
            'price',
            'gift',
            'gift_url',
            'description',
            'visible',
            'date_expires',
        ]
        labels = {
            'price': '',
            'receiver': '',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5})
        }

    def clean_price(self):
        """
        When updating price has to be equal or higher
        than money collected. Otherwise it would collected
        field would be pointless
        """
        price = self.cleaned_data['price']
        if price < self.instance.collected():
            msg = "Cena nie może być niższa niż kwota do tej pory zebrana"
            raise forms.ValidationError(msg)
        return price

    def clean_date_expires(self):
        created = self.instance.created
        date_expires = self.cleaned_data['date_expires']
        max_length = created + timedelta(days=183)
        if date_expires > max_length:
            msg = 'Zbiórka nie może trwać dłużej niż 183 dni od utworzenia'
            raise forms.ValidationError(msg)
        today = datetime.now().date()
        if date_expires <= today:
            raise forms.ValidationError(
                'Data wygraśnięcia musi być w przyszłości'
            )
        return date_expires


class VisibleForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            'guests'
        ]


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = [
            'receiver',
            'sender',
            'subject',
            'content',
        ]

    def clean(self):
        receiver = self.cleaned_data['receiver']
        sender = self.cleaned_data['sender']
        if receiver == sender:
            raise forms.ValidationError(
                'Odbiorca i nadawca nie mogą być tacy sami'
            )


class DonateForm(forms.ModelForm):
    comment = forms.CharField(
        widget=forms.Textarea({'rows': 5}),
        help_text='Jeśli chcesz możesz przekazać informacje obdarowanemu',
        required=False,
    )

    class Meta:
        model = Donation
        fields = [
            'amount',
            'comment',
        ]
        help_texts = {
            'amount': 'Minimalna wielkośc składki to 1 PLN',
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        minimal_amount = 1
        if amount < minimal_amount:
            err = f'Wprowadzona kwota: {amount:.2f}. Minimalna kwota to 1 PLN'
            raise forms.ValidationError(err)
        return amount
