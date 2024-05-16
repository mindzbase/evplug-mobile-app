from utils import format_time_with_leading_zeros


def get_invoice_html(invoice_details, organisation_details):
    from dateutil.relativedelta import relativedelta
    import datetime

    utc_offset = int(organisation_details.get("utc_offset", "0"))
    invoice_date = invoice_details.get("invoice_date") + relativedelta(
        minutes=utc_offset
    )
    invoice_date = invoice_date.date()
    session_start_time = invoice_details.get("start_time") + relativedelta(
        minutes=utc_offset
    )
    session_stop_time = invoice_details.get("stop_time") + relativedelta(
        minutes=utc_offset
    )
    duration = invoice_details.get("duration")

    if duration:
        duration = datetime.timedelta(seconds=int(duration))
        duration = format_time_with_leading_zeros(duration)
    tax_on_invoice = f"""
        <div>
            Total Amount : <span style="font-weight: 400;">{
                invoice_details.get('charging_cost')}</span>
        </div>
        <div style="margin-top:8px;">
            Tax ({
                int(invoice_details.get('tax_percentage'))
                if invoice_details.get('tax_percentage') else "5"}%) : <span
            style="font-weight: 400;">{(
                invoice_details.get('charging_cost_with_tax') -
                invoice_details.get('charging_cost')):.2f}</span>
        </div>
        <div style="margin-top:8px;">
            Cost with Tax : <span
            style="font-weight: 400;">{
                invoice_details.get('charging_cost_with_tax')}</span>
        </div>
        <div style="margin-top:8px;">
            Service_fee : <span
            style="font-weight: 400;">{
                invoice_details.get('gateway_fee')}</span>
        </div>
        <div style="margin-top:8px;">
            Idle Vehicle Cost : <span
            style="font-weight: 400;">{
                invoice_details.get("idle_charging_cost", 0)}</span>
        </div>
        <div style="margin-top:8px;">
            Final Amount : <span style="font-weight: 500;">{(
                invoice_details.get('charging_cost_with_tax')
                + invoice_details.get("idle_charging_cost", 0)
                + invoice_details.get("gateway_fee", 0)
                ):.2f}</span>
        </div>
    """
    without_tax_on_invoice = f"""
        <div>
            Total Amount : <span style="font-weight: 400;">{
                (invoice_details.get('charging_cost_with_tax')
                + invoice_details.get("idle_charging_cost", 0)
                + invoice_details.get("gateway_fee", 0)
                ):.2f}</span>
        </div>
    """
    html_header = """
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invoice</title>
                <!-- online fonts -->
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link
                href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap"
                rel="stylesheet">
            <link
                href="https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;400;500;600;700;800;900&family=Poppins:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,100;1,200;1,300;1,400;1,500;1,600;1,700;1,800;1,900&display=swap"
                rel="stylesheet">
            <style>
                body{
                    font-family: 'Poppins';
                    font-style: normal;
                    color: #000000;
                }
                .hrborder{
                    border: 1px solid #DEE2E6;
                    margin-top: 8px;
                }
                .parent{
                    display: table;
                    width: 100%;
                    table-layout: fixed;
                    border-collapse: separate;
                    border-spacing: 10px;
                }
                .child{
                    display: table-cell;
                    font-size: 20px;
                    line-height: 24px;
                }
                .child:first-child {
                    float: left;
                    width: 51%;
                }

                .child:last-child {
                    float: right;
                    width: 49%;
                }

                .bolder{
                    font-weight: 600;
                }
                .bold{
                    font-weight: 500;
                }
                .normal{
                    font-weight: 400;
                }
                .logo{
                max-width: 100%;
                }
                .logo>img{
                    max-width: 100%;
                    height: 80px;
                    object-fit: cover;
                }
            </style>
        </head>
    """
    html_code = f"""
    <!DOCTYPE html>
    <html lang="en">
    {html_header}
    <body>
        <div style="position: relative;">
            <div class="logo">
                <img
                    {f"src='{organisation_details.get('logo_url')}'" if organisation_details.get('logo_url') else ''}
                    alt="{organisation_details.get('org_name')}"
                >
            </div>
            <div style="
                font-weight: 500;
                font-size: 48px;
                line-height: 36px;
                text-transform: uppercase;
                position: absolute;
                left: 43%;
                top: 17px;">INVOICE
            </div>
            <div style="position:absolute;
                    left:78.1%; top:13px;">
                <div style="
                    font-weight: 500;
                    font-size: 20px;
                    line-height: 15px;
                    ">Invoice ID : <span style="font-weight: 400;">{
                        invoice_details.get('invoice_id')}</span></div>
                <div style="
                    font-weight: 500;
                    font-size: 20px;
                    line-height: 15px;
                    color: #000000;
                    margin-top: 16px;
                    ">Date : <span style="font-weight: 400;">{invoice_date}</span></div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bolder" style="margin-top:16px;">
                <div class="child">Invoice From</div>
                <div class="child">Invoice To</div>
            </div>
            <div class="hrborder"></div>
            <div class="parent normal">
                <div class="child">
                    <div style="margin-top:16px;">{
                        organisation_details.get('org_name')}</div>
                    <div style="margin-top:16px;">{
                        organisation_details.get('email')}</div>
                    <div style="margin-top:16px;">
                        <span class="bold">TAXIN : </span>{
                            organisation_details.get('vat')}
                    </div>
                </div>
                <div class="child">
                    <div style="margin-top:16px;">{invoice_details.get('name')}</div>
                    <div style="margin-top:16px;">{invoice_details.get('phone')}</div>
                </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bolder" style="margin-top:16px;">
                <div class="child">Charger Details</div>
                <div class="child">Session Details </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bold">
                <div class="child">
                    <div>
                        Charger ID : <span style="font-weight: 400;">{
                            invoice_details.get('charger_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Connector ID : <span style="font-weight: 400;">{
                            invoice_details.get('connector_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Max Output (kWh): <span style="font-weight: 400;">{
                            invoice_details.get('max_output')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Address : <span style="font-weight: 400;">{
                            invoice_details.get('location_name')}</span>
                    </div>
                </div>
                <div class="child">
                    <div>
                        Session ID : <span style="font-weight: 400;">{
                            invoice_details.get('session_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Energy Used : <span style="font-weight: 400;">{
                            invoice_details.get('session_energy_used'):.2f} kW</span>
                    </div>
                    <div style="margin-top:8px;">
                        Session Start Time : <span style="font-weight: 400;">{
                            session_start_time}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Session End Time : <span style="font-weight: 400;">{
                            session_stop_time
                        }</span>
                    </div>
                    <div style="margin-top:8px;">
                        Bill By : <span style="font-weight: 400;">{invoice_details.get('bill_by')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Price : <span style="font-weight: 400;">{invoice_details.get('price')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Duration : <span style="font-weight: 400;">{duration}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Amount : <span style="font-weight: 400;">{
                            invoice_details.get('charging_cost')}</span>
                    </div>
                </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bold">
                <div class="child" style="width: unset;">
                {tax_on_invoice if organisation_details.get('show_tax_on_invoice') else without_tax_on_invoice}
                </div>
                <div class="child" style="width: unset;">
                    <div style="text-align: end;">
                        Final Payable  Amount :
                    </div>
                    <div style="
                        margin-top:8px;
                        text-align: end;
                        font-size: 30px;
                    ">{organisation_details.get('currency')} {
                            (invoice_details.get('charging_cost_with_tax')
                            + invoice_details.get("idle_charging_cost", 0)
                            + invoice_details.get("gateway_fee", 0)
                            ):.2f}
                    </div>
                </div>
            </div>
        </div>
    </body>
</html>
    """
    return html_code


def get_email_html(invoice_details, organisation_details):
    from dateutil.relativedelta import relativedelta

    utc_offset = int(organisation_details.get("utc_offset", "0"))
    invoice_date = invoice_details.get("invoice_date") + relativedelta(
        minutes=utc_offset
    )
    invoice_date = invoice_date.date()
    session_start_time = invoice_details.get("start_time") + relativedelta(
        minutes=utc_offset
    )
    session_stop_time = invoice_details.get("stop_time") + relativedelta(
        minutes=utc_offset
    )
    duration = invoice_details.get("duration")

    html_header = """
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invoice</title>
                <!-- online fonts -->
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link
                href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap"
                rel="stylesheet">
            <link
                href="https://fonts.googleapis.com/css2?family=Inter:wght@100;200;300;400;500;600;700;800;900&family=Poppins:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,100;1,200;1,300;1,400;1,500;1,600;1,700;1,800;1,900&display=swap"
                rel="stylesheet">
            <style>
                body{
                    font-family: 'Poppins';
                    font-style: normal;
                    color: #000000;
                }
                .hrborder{
                    border: 1px solid #DEE2E6;
                    margin-top: 8px;
                }
                .parent{
                    display: table;
                    width: 100%;
                    table-layout: fixed;
                    border-collapse: separate;
                    border-spacing: 10px;
                }
                .child{
                    display: table-cell;
                    font-size: 20px;
                    line-height: 24px;
                }
                .child:first-child {
                    float: left;
                    width: 51%;
                }

                .child:last-child {
                    float: right;
                    width: 49%;
                }

                .bolder{
                    font-weight: 600;
                }
                .bold{
                    font-weight: 500;
                }
                .normal{
                    font-weight: 400;
                }
                .logo{
                max-width: 100%;
                }
                .logo>img{
                    max-width: 100%;
                    height: 80px;
                    object-fit: cover;
                }
            </style>
        </head>
    """
    html_code = f"""
    <!DOCTYPE html>
    <html lang="en">
    {html_header}
    <body>
        <div style="position: relative;">
            <div style="display:flex; justify-content: space-between;
            align-items:center;">
                <div class="logo" style="width: 33.33%;">
                    <img
                        src="{organisation_details.get('logo_url')}"
                        alt="{organisation_details.get('org_name')}"
                    >
                </div>
                <div style="
                    font-weight: 500;
                    font-size: 48px;
                    line-height: 36px;
                    text-transform: uppercase;
                    width: 33.33%;
                    text-align: center;
                    margin: auto;
                    ">INVOICE
                </div>
                <div  style="width: 33.33%;text-align: end; margin: auto;">
                    <div style="
                        font-weight: 500;
                        font-size: 20px;
                        line-height: 15px;
                        ">Invoice ID : <span style="font-weight: 400;">{
                            invoice_details.get('invoice_id')}</span>
                    </div>
                    <div style="
                        font-weight: 500;
                        font-size: 20px;
                        line-height: 15px;
                        color: #000000;
                        margin-top: 16px;
                        ">Date : <span style="font-weight: 400;">{invoice_date}</span>
                    </div>
                </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bolder" style="margin-top:16px;">
                <div class="child">Invoice From</div>
                <div class="child">Invoice To</div>
            </div>
            <div class="hrborder"></div>
            <div class="parent normal">
                <div class="child">
                    <div style="margin-top:16px;">{
                        organisation_details.get('org_name')}</div>
                    <div style="margin-top:16px;">{
                        organisation_details.get('email')}</div>
                    <div style="margin-top:16px;">
                        <span class="bold">TAXIN : </span>{
                            organisation_details.get('vat')}
                    </div>
                </div>
                <div class="child">
                    <div style="margin-top:16px;">{invoice_details.get('name')}</div>
                    <div style="margin-top:16px;">{invoice_details.get('phone')}</div>
                </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bolder" style="margin-top:16px;">
                <div class="child">Charger Details</div>
                <div class="child">Session Details </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bold">
                <div class="child">
                    <div>
                        Charger ID : <span style="font-weight: 400;">{
                            invoice_details.get('charger_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Connector ID : <span style="font-weight: 400;">{
                            invoice_details.get('connector_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Address : <span style="font-weight: 400;">{
                            invoice_details.get('location_name')}</span>
                    </div>
                </div>
                <div class="child">
                    <div>
                        Session ID : <span style="font-weight: 400;">{
                            invoice_details.get('session_id')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Energy Used : <span style="font-weight: 400;">{
                            invoice_details.get('session_energy_used'):.2f} kW</span>
                    </div>
                    <div style="margin-top:8px;">
                        Session Start Time : <span style="font-weight: 400;">{
                            session_start_time}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Session End Time : <span style="font-weight: 400;">{
                            session_stop_time
                        }</span>
                    </div>
                    <div style="margin-top:8px;">
                        Duration : <span style="font-weight: 400;">{duration}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Amount : <span style="font-weight: 400;">{
                            invoice_details.get('charging_cost')}</span>
                    </div>
                </div>
            </div>
            <div class="hrborder"></div>
            <div class="parent bold">
                <div class="child" style="width: unset;">
                    <div>
                        Total Amount : <span style="font-weight: 400;">{
                            invoice_details.get('charging_cost')}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Tax ({
                            int(invoice_details.get('tax_percent'))
                            if invoice_details.get('tax_percent') else "5"}%) : <span
                        style="font-weight: 400;">{(
                            invoice_details.get('charging_cost_with_tax') -
                            invoice_details.get('charging_cost')):.2f}</span>
                    </div>
                    <div style="margin-top:8px;">
                        Final Amount : <span style="font-weight: 500;">{
                            invoice_details.get('charging_cost_with_tax')}</span>
                    </div>
                </div>
                <div class="child" style="width: unset;">
                    <div style="text-align: end;">
                        Final Payable  Amount :
                    </div>
                    <div style="
                        margin-top:8px;
                        text-align: end;
                        font-size: 30px;
                    ">{organisation_details.get('currency')} {
                        invoice_details.get('charging_cost_with_tax')}
                    </div>
                </div>
            </div>
        </div>
    </body>
</html>
    """
    return html_code


def verify_email_html(organisation_details, verification_url, valid_till):
    header = """
        <!DOCTYPE html>
        <html lang="en">

        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Document</title>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@100;200;300;400;500;600;700;800;900&display=swap" rel="stylesheet">
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    text-decoration: none;
                    font-family: 'Archivo', sans-serif, Helvetica, Calibri, Arial, Roboto;
                }

                body {
                    display: inline-block;
                    background: #F8F9FA;
                }

                .emailbody {
                    background: #F8F9FA;
                    width: 100%;
                    height: 100%;
                    display: inline-block;
                }

                .wrapper {
                    position: absolute;
                    transform: translate(-50%);
                    left: 50%;
                    width: fit-content;
                    display: block;
                    margin-left: auto;
                    margin-right: auto;
                }

                .wrapper .logo {
                    margin-top: 48px;
                    width: 125px;
                }

                .wrapper .logo img {
                    max-width:100%
                }

                .wrapper .greeting-box {
                    border-radius: 8px;
                    border: 1px solid #E6E2DE;
                    background: #FFF;
                    box-shadow: 0px 2px 4px -1px rgba(0, 0, 0, 0.06), 0px 4px 6px -1px rgba(0, 0, 0, 0.10);
                    padding: 40px;
                    margin-top: 16px;
                }

                .welcome-heading {
                    color: #292321;
                    font-size: 24px;
                    font-style: normal;
                    font-weight: 600;
                    line-height: 32px;
                }

                .message {
                    color: #574F49;
                    font-size: 14px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 24px;
                    margin-top: 24px;
                }

                .message span {
                    font-weight: 600;
                }

                .activateMyAccountBtn {
                    border-radius: 6px;
                    background: #40C057;
                    padding: 12px 24px;
                    margin-top: 40px;
                    border: 0;
                    color: white;
                    width: auto;
                    display: block;
                    margin-left: auto;
                    margin-right: auto;

                }

                .activateMyAccountBtn a{
                    color: white;
                }

                .expiry-message {
                    color: #574F49;
                    font-size: 14px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 24px;
                    margin-top: 16px;
                }

                .regards {
                    font-size: 14px;
                    font-style: normal;
                    line-height: 24px;
                    margin-top: 24px;
                }

                .regards .happy-charging-text {
                    font-weight: 500;
                    color: #292321;
                }

                .regards .about-team {
                    font-weight: 400;
                    color: #574F49;
                }

                .help-box {
                    border-radius: 8px;
                    border: 1px solid #E6E2DE;
                    background: #FFF;
                    box-shadow: 0px 2px 4px -1px rgba(0, 0, 0, 0.06), 0px 4px 6px -1px rgba(0, 0, 0, 0.10);
                    padding: 40px;
                    margin-top: 16px;
                    margin-bottom: 48px;
                }

                .help-box .need-help-text {
                    color: #292321;
                    font-size: 16px;
                    font-style: normal;
                    font-weight: 600;
                    line-height: 24px;
                }

                .help-box .support-msg {
                    color: #574F49;
                    font-size: 14px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 24px;
                }

                .help-box .support-msg a {
                    color: #40C057;
                }
            </style>
        </head>
    """
    html = f"""
        {header}
        <body>
            <div class="emailbody">
                <div class="wrapper">
                    <div class="logo">
                        <img src="{organisation_details.get('logo_url')}" alt="logo">
                    </div>
                    <div class="greeting-box">
                        <div class="welcome-heading">Welcome to {
                            organisation_details.get('org_name')}</div>
                        <div class="message">
                            <p>
                                Thank you for registering with {
                                    organisation_details.get('org_name')}.
                            </p>
                            <p>
                                To complete the activation of your account, click on the
                                <span>
                                    “Activate my account”
                                </span>
                                button:
                            </p>
                        </div>
                        <button class="activateMyAccountBtn" style="background: {
                            organisation_details.get('primary_color')}">
                            <a href="{verification_url}">Activate my account</a>
                        </button>
                        <div class="expiry-message">This button expires in {valid_till} minutes. Didn't ask for this email? Just ignore
                            this
                            mail.
                        </div>
                        <div class="regards">
                            <div class="happy-charging-text">Happy Charging,</div>
                            <div class="about-team">Team {
                                organisation_details.get('org_name')}</div>
                        </div>
                    </div>
                    <div class="help-box">
                        <div class="need-help-text">We are here to help?</div>
                        <div class="support-msg">
                            Have questions? We have answers! Contact our support team by
                            <a style="color: {
                                organisation_details.get('primary_color')
                                }" href="mailto:{
                                organisation_details.get('email')}">Email.</a>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    return html


def verified_html(primary_color, logo_url, user_email, org_name):
    script = """
        <script>
            let timer = 10
            let timerElement = document.getElementById('timer')
            let intervalID = setInterval(() => {
                timer -= 1
                if (timer < 10)
                    timerElement.innerText = "0" + timer
                else
                    timerElement.innerText = timer
                if (timer <= 0) {
                    clearInterval(intervalID)
                    window.close()
                }
            }, 1000);
        </script>
    """
    header = """
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Verified!</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@100;200;300;400;500;600;700;800;900&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300;1,400;1,500&family=DM+Sans:wght@400;500;700&family=Space+Mono&display=swap');
            </style>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    text-decoration: none;
                }

                body {
                    display: inline-block;
                }

                .emailbody {
                    background: #F8F9FA;
                    width: 100vw;
                    height: 100vh;
                    display: inline-block;
                }

                .wrapper {
                    position: absolute;
                    transform: translate(-50%, -50%);
                    left: 50%;
                    top: 50%;
                }

                .wrapper .greeting-box {
                    border-radius: 8px;
                    border: 1px solid #E6E2DE;
                    background: #FFF;
                    box-shadow: 0px 2px 4px -1px rgba(0, 0, 0, 0.06), 0px 4px 6px -1px rgba(0, 0, 0, 0.10);
                    padding: 40px;
                    margin-top: 16px;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                }

                .welcome-heading {
                    color: #292321;
                    font-family: Archivo;
                    font-size: 24px;
                    font-style: normal;
                    font-weight: 600;
                    line-height: 32px;
                    margin-top: 24px;
                }

                .message {
                    color: #574F49;
                    font-family: Archivo;
                    font-size: 14px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 24px;
                    margin-top: 8px;
                }

                .message span {
                    font-weight: 600;
                }

                .closing-window {
                    color: #574F49;
                    text-align: center;
                    font-family: Archivo;
                    font-size: 14px;
                    font-style: normal;
                    font-weight: 400;
                    line-height: 24px;
                    margin-top: 16px;
                }

                .hrborder {
                    width: 100%;
                    height: 1px;
                    background: #E6E2DE;
                    margin-top: 80px;
                    margin-bottom: 16px;
                }

                .logo {
                    width: 125px;
                    margin-left: auto;
                    margin-right: auto;
                }

                .logo img {
                    max-width: 100%;
                }
            </style>
        </head>
    """
    html = f"""
        <!DOCTYPE html>
        <html lang="en">
        {header}
        <body>
            <div class="emailbody">
                <div class="wrapper">
                    <div class="greeting-box">
                        <svg width="56" height="56" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <circle cx="28" cy="28" r="28" fill="#40C057" fill-opacity="0.12" />
                            <path
                                d="M32.29 24.71C32.383 24.8037 32.4936 24.8781 32.6154 24.9289C32.7373 24.9797 32.868 25.0058 33 25.0058C33.132 25.0058 33.2627 24.9797 33.3846 24.9289C33.5064 24.8781 33.617 24.8037 33.71 24.71L37.71 20.71C37.8983 20.5217 38.0041 20.2663 38.0041 20C38.0041 19.7337 37.8983 19.4783 37.71 19.29C37.5217 19.1017 37.2663 18.9959 37 18.9959C36.7337 18.9959 36.4783 19.1017 36.29 19.29L33 22.59L31.71 21.29C31.6168 21.1968 31.5061 21.1228 31.3842 21.0723C31.2624 21.0219 31.1319 20.9959 31 20.9959C30.7337 20.9959 30.4783 21.1017 30.29 21.29C30.1968 21.3832 30.1228 21.4939 30.0723 21.6158C30.0219 21.7376 29.9959 21.8681 29.9959 22C29.9959 22.2663 30.1017 22.5217 30.29 22.71L32.29 24.71ZM37 24C36.7348 24 36.4804 24.1054 36.2929 24.2929C36.1054 24.4804 36 24.7348 36 25V34C36 34.2652 35.8946 34.5196 35.7071 34.7071C35.5196 34.8946 35.2652 35 35 35H21C20.7348 35 20.4804 34.8946 20.2929 34.7071C20.1054 34.5196 20 34.2652 20 34V24.41L25.88 30.3C26.4412 30.8567 27.1995 31.1693 27.99 31.17C28.8004 31.1658 29.5764 30.8425 30.15 30.27L31.87 28.55C32.0583 28.3617 32.1641 28.1063 32.1641 27.84C32.1641 27.5737 32.0583 27.3183 31.87 27.13C31.6817 26.9417 31.4263 26.8359 31.16 26.8359C30.8937 26.8359 30.6383 26.9417 30.45 27.13L28.7 28.88C28.5131 29.0632 28.2618 29.1659 28 29.1659C27.7382 29.1659 27.4869 29.0632 27.3 28.88L21.41 23H27C27.2652 23 27.5196 22.8946 27.7071 22.7071C27.8946 22.5196 28 22.2652 28 22C28 21.7348 27.8946 21.4804 27.7071 21.2929C27.5196 21.1054 27.2652 21 27 21H21C20.2044 21 19.4413 21.3161 18.8787 21.8787C18.3161 22.4413 18 23.2044 18 24V34C18 34.7957 18.3161 35.5587 18.8787 36.1213C19.4413 36.6839 20.2044 37 21 37H35C35.7956 37 36.5587 36.6839 37.1213 36.1213C37.6839 35.5587 38 34.7957 38 34V25C38 24.7348 37.8946 24.4804 37.7071 24.2929C37.5196 24.1054 37.2652 24 37 24Z"
                                fill="{primary_color}" />
                        </svg>

                        <div class="welcome-heading">Welcome to {org_name}</div>
                        <div class="message">
                            <p style="width: 38ch;text-align: center;">
                                Your email address
                                <span>
                                    {user_email}
                                </span>
                                has been successfully verified.
                            </p>
                        </div>
                    </div>
                    <div class="closing-window">This page will close in
                        <span style="color: {primary_color};">00:
                            <span id="timer">10</span>
                        </span>
                    </div>
                    <div class="hrborder"></div>
                    <div class="logo">
                        <img src="{logo_url}" alt="logo">
                    </div>
                </div>
            </div>
            {script}
        </body>
        </html>
    """

    return html
