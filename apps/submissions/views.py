import os
import tempfile
import shutil
from urllib.parse import urlencode
import uuid

from django.core.files import File
from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.db import transaction
from fpdf import FPDF
import re

from apps.records.graphics import queue_graphics
from apps.records.filtering import apply_record_sort
from src import midi_reader, tessitura, utils
from src.tessitura import TessPassContainer
from apps.records.models import Record
from apps.records.columns import (
    AVAILABLE_COLUMNS,
    DEFAULT_REVIEW_COLUMNS,
    get_display_columns,
)
from .forms import SubmissionForm, ReviewerEditForm


def safe_filename_part(value):
    value = re.sub(r'[\\/:*?"<>|]', "-", str(value)).strip()
    return value or "new"

def notify_admins_of_submission(request, record):
    review_url = request.build_absolute_uri(
        reverse("submissions:review_detail", args=[record.submission_group])
    )
    send_mail(
        subject=f"New submission for review: {record.filename}",
        message=(
            f'{record.submitted_by} submitted "{record.filename}" '
            f"({record.composer}) for review.\n\n"
            f"Review it here: {review_url}"
        ),
        from_email=None,
        recipient_list=[settings.NOTIFICATION_EMAIL],
    )


@login_required
def submit_form(request):
    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)

        if form.is_valid():
            title = form.cleaned_data["title"]
            larger_work = form.cleaned_data["larger_work"]
            uploaded_file = form.cleaned_data["midi_file"]
            filename = os.path.splitext(uploaded_file.name)[0]
            composer = form.cleaned_data["composer"]
            style = form.cleaned_data["style"]
            style_other = form.cleaned_data["style_other"]
            author = form.cleaned_data.get("author", "")
            initial_key = form.cleaned_data["initial_key"]

            # This is the clef the submitted MIDI is written in.
            written_clef_range = form.cleaned_data.get("written_clef_range") or None

            performing_forces = "solo"
            voice_part = form.cleaned_data["voice_part"]
            additional_comments = form.cleaned_data.get(
                "additional_comments",
                "",
            )

            work_dir = tempfile.mkdtemp(prefix="tessitura_")
            output_dir = os.path.join(work_dir, "results")
            os.makedirs(output_dir, exist_ok=True)

            group_id = uuid.uuid4()

            try:
                midi_path = os.path.join(work_dir, uploaded_file.name)

                with open(midi_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                with midi_reader.MidiParser(midi_path) as parser:
                    status = parser.parse_midi()

                    if status == -1:
                        error_msg = (
                            parser.error_message
                            or "Could not parse MIDI file."
                        )
                        form.add_error(None, error_msg)

                        return render(
                            request,
                            "submissions/submit_form.html",
                            {"form": form},
                        )

                    notes = parser.get_notes()

                    if notes == -1:
                        error_msg = (
                            parser.error_message
                            or "Could not extract notes from MIDI file."
                        )
                        form.add_error(None, error_msg)

                        return render(
                            request,
                            "submissions/submit_form.html",
                            {"form": form},
                        )

                notes = parser.post_process(notes)

                if notes == -1:
                    error_msg = (
                        parser.error_message
                        or "Could not process notes from MIDI file."
                    )
                    form.add_error(None, error_msg)

                    return render(
                        request,
                        "submissions/submit_form.html",
                        {"form": form},
                    )

                written_clef_range = form.cleaned_data.get("written_clef_range") or None
                tess_clef = (
                    None
                    if not written_clef_range or written_clef_range.lower() in ("unknown", "n/a")
                    else written_clef_range.lower()
                )

                tesses, passaggios, _ = tessitura.get_tessitura_and_passaggio(
                    notes,
                    tess_clef,
                )

                keep_private = form.cleaned_data.get(
                    "keep_private",
                    False,
                )

                initial_status = "pending"

                for tess, passaggio in zip(tesses, passaggios):
                    record = Record.objects.create(
                        submitted_by=request.user,
                        submission_group=group_id,

                        filename=filename,
                        title=title,
                        larger_work=larger_work,
                        composer=composer,
                        author=author,

                        initial_key=initial_key,
                        style=style,
                        style_other=style_other,

                        # Clef used as the starting interpretation
                        # for this submission.
                        written_clef_range=written_clef_range,

                        # Clef represented by this particular record.
                        clef_range=tess.clef_range,

                        performing_forces=performing_forces,
                        voice_part=voice_part,
                        additional_comments=additional_comments,

                        status=initial_status,

                        q1_freq=tess.lowFreq,
                        q1_pitch=tess.lowNote,
                        q1_octave=tess.lowOctave,

                        q3_freq=tess.highFreq,
                        q3_pitch=tess.highNote,
                        q3_octave=tess.highOctave,

                        cycle_dose=tess.cycle_dose,
                        time_dose=tess.time_dose,
                        rest_time=tess.rest_time,
                        total_time=tess.total_time,

                        median_freq=tess.median_freq,

                        min_freq=tess.min_pitch,
                        max_freq=tess.max_pitch,

                        hvhp_time_dose=passaggio.hvhp.time_dose,
                        hvmp_time_dose=passaggio.hvmp.time_dose,
                        hvlp_time_dose=passaggio.hvlp.time_dose,

                        mvhp_time_dose=passaggio.mvhp.time_dose,
                        mvmp_time_dose=passaggio.mvmp.time_dose,
                        mvlp_time_dose=passaggio.mvlp.time_dose,

                        lvhp_time_dose=passaggio.lvhp.time_dose,
                        lvmp_time_dose=passaggio.lvmp.time_dose,
                        lvlp_time_dose=passaggio.lvlp.time_dose,
                    )

                    with open(midi_path, "rb") as midi_f:
                        record.midi_file.save(
                            uploaded_file.name,
                            File(midi_f),
                            save=True,
                        )

                    pdf = FPDF()

                    pdf.add_font(
                        "times_new",
                        "",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "B",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Bold.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "I",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Italic.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "BI",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Bold Italic.ttf",
                            )
                        ),
                    )

                    pdf.add_page()

                    container = TessPassContainer(
                        tess,
                        passaggio,
                        title,
                        pdf,
                        output_dir=output_dir,
                        submitted_by=(
                            f"{request.user.first_name} "
                            f"{request.user.last_name}"
                        ),
                    )

                    container.ensure_musescore_configured()
                    container.write_to_pdf()

                    pdf_filename = (
                        f"{safe_filename_part(record.title)}-"
                        f"{record.clef_range}-Tessituragram-"
                        f"{uuid.uuid4().hex[:8]}.pdf"
                    )

                    pdf_path = os.path.join(
                        work_dir,
                        pdf_filename,
                    )

                    pdf.output(pdf_path)

                    with open(pdf_path, "rb") as pdf_f:
                        record.pdf_file.save(
                            pdf_filename,
                            File(pdf_f),
                            save=True,
                        )

                    if not keep_private:
                        notify_admins_of_submission(
                            request,
                            record,
                        )

                transaction.on_commit(queue_graphics)
                return redirect("submissions:submission_success")

            finally:
                shutil.rmtree(
                    work_dir,
                    ignore_errors=True,
                )

    else:
        form = SubmissionForm()

    return render(
        request,
        "submissions/submit_form.html",
        {"form": form},
    )


@login_required
def submission_success(request):
    return render(request, "submissions/submission_success.html")


@staff_member_required
def review_list(request):
    records = Record.objects.filter(
        status="pending",
        is_deleted=False,
    )

    representative_ids = list(
        records
        .order_by("submission_group", "-created_at")
        .distinct("submission_group")
        .values_list("id", flat=True)
    )

    records = (
        Record.objects
        .filter(id__in=representative_ids)
        .select_related("submitted_by")
    )

    # --------------------------------------------------
    # Sorting
    # --------------------------------------------------

    sort = request.GET.get("sort", "created_at")
    records = apply_record_sort(records, sort)

    # --------------------------------------------------
    # Display columns
    # --------------------------------------------------

    selected_columns, display_columns = get_display_columns(
        request,
        DEFAULT_REVIEW_COLUMNS,
    )

    # --------------------------------------------------
    # Query parameters
    # --------------------------------------------------

    active_filters = [
        (key, value)
        for key, values in request.GET.lists()
        for value in values
        if value
    ]

    search_querystring = urlencode(
        [
            (key, value)
            for key, values in request.GET.lists()
            if key != "sort"
            for value in values
            if value
        ]
    )

    return render(
        request,
        "submissions/review_list.html",
        {
            "records": records,
            "current_sort": sort,
            "active_filters": active_filters,
            "search_querystring": search_querystring,
            "all_columns": AVAILABLE_COLUMNS,
            "selected_columns": selected_columns,
            "display_columns": display_columns,
        },
    )

@staff_member_required
def review_detail(request, pk):
    group_records = Record.objects.filter(
        submission_group=pk,
        status="pending",
        is_deleted=False,
    )

    if not group_records.exists():
        raise Http404

    record = group_records.first()

    if request.method == "POST":
        action = request.POST.get("action")

    if request.method == "POST" and request.user.is_staff:
        action = request.POST.get("action")

        if action == "approve":
            approval_at = timezone.now()

            for item in group_records:
                item.status = "public"
                item.approval_at = approval_at
                item.approval_by = request.user
                item.save()

            return redirect("submissions:review_list")

        elif action == "reject":
            for item in group_records:
                item.status = "rejected"
                item.save()

            return redirect("submissions:review_list")

        elif "status" in request.POST:
            new_status = request.POST.get("status")

            if new_status in dict(Record.STATUS_CHOICES):
                for item in group_records:
                    item.status = new_status

                    if new_status == "public":
                        item.approval_at = timezone.now()
                        item.approval_by = request.user

                    item.save()

            return redirect("submissions:review_detail", pk=pk)

    return render(
        request,
        "submissions/review_detail.html",
        {
            "record": record,
            "group_records": group_records,
            "bass_record": group_records.filter(clef_range="Bass").first(),
            "treble_record": group_records.filter(clef_range="Treble").first(),
            "none_record": group_records.filter(clef_range="None").first(),
        },
    )

@staff_member_required
def edit_resubmit(request, pk):
    record = get_object_or_404(
        Record,
        pk=pk,
        is_deleted=False,
    )

    group_records = list(
        Record.objects.filter(
            submission_group=record.submission_group,
            is_deleted=False,
        )
    )

    if request.method == "POST":
        form = ReviewerEditForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            uploaded_file = form.cleaned_data.get("midi_file")

            if not uploaded_file and not record.midi_file:
                form.add_error(
                    None,
                    "No MIDI file is on record. Please upload one "
                    "to reprocess this submission.",
                )
                return render(
                    request,
                    "submissions/edit_resubmit.html",
                    {
                        "form": form,
                        "record": record,
                    },
                )

            work_dir = tempfile.mkdtemp(
                prefix="tessitura_edit_"
            )
            output_dir = os.path.join(
                work_dir,
                "results",
            )
            os.makedirs(
                output_dir,
                exist_ok=True,
            )

            try:
                # ---------------------------------------------------------
                # Get MIDI file
                # ---------------------------------------------------------
                if uploaded_file:
                    midi_path = os.path.join(
                        work_dir,
                        uploaded_file.name,
                    )

                    with open(midi_path, "wb") as f:
                        for chunk in uploaded_file.chunks():
                            f.write(chunk)

                else:
                    midi_path = os.path.join(
                        work_dir,
                        os.path.basename(record.midi_file.name),
                    )

                    with record.midi_file.open("rb") as source:
                        with open(midi_path, "wb") as dest:
                            shutil.copyfileobj(source, dest)

                # ---------------------------------------------------------
                # Parse MIDI
                # ---------------------------------------------------------
                with midi_reader.MidiParser(midi_path) as parser:
                    status = parser.parse_midi()

                    if status == -1:
                        form.add_error(
                            None,
                            parser.error_message
                            or "Could not parse MIDI file.",
                        )
                        return render(
                            request,
                            "submissions/edit_resubmit.html",
                            {
                                "form": form,
                                "record": record,
                            },
                        )

                    notes = parser.get_notes()

                    if notes == -1:
                        form.add_error(
                            None,
                            parser.error_message
                            or "Could not extract notes from MIDI file.",
                        )
                        return render(
                            request,
                            "submissions/edit_resubmit.html",
                            {
                                "form": form,
                                "record": record,
                            },
                        )

                # Same post-processing as normal submissions.
                notes = parser.post_process(notes)

                if notes == -1:
                    error_msg = (
                        parser.error_message
                        or "Could not process notes from MIDI file."
                    )
                    form.add_error(None, error_msg)

                    return render(
                        request,
                        "submissions/submit_form.html",
                        {"form": form},
                    )

                # ---------------------------------------------------------
                # Get written/original clef
                # ---------------------------------------------------------
                written_clef_range = form.cleaned_data.get("written_clef_range") or None
                tess_clef = (
                    None
                    if not written_clef_range or written_clef_range.lower() in ("unknown", "n/a")
                    else written_clef_range.lower()
                )

                tesses, passaggios, _ = tessitura.get_tessitura_and_passaggio(
                    notes,
                    tess_clef,
                )

                # ---------------------------------------------------------
                # Filename
                # ---------------------------------------------------------
                if uploaded_file:
                    new_filename = os.path.splitext(
                        uploaded_file.name
                    )[0]
                else:
                    new_filename = record.filename

                new_clefs = {tess.clef_range for tess in tesses}

                for old_record in group_records:
                    if old_record.clef_range not in new_clefs:
                        old_record.delete()
                for tess, passaggio in zip(
                    tesses,
                    passaggios,
                ):
                    target = next(
                        (
                            r
                            for r in group_records
                            if r.clef_range == tess.clef_range
                        ),
                        None,
                    )

                    if target is None:
                        target = Record(
                            submitted_by=record.submitted_by,
                            submission_group=record.submission_group,
                        )

                    # -----------------------------------------------------
                    # General submission information
                    # -----------------------------------------------------
                    target.title = form.cleaned_data["title"]

                    target.larger_work = form.cleaned_data[
                        "larger_work"
                    ]

                    target.composer = form.cleaned_data[
                        "composer"
                    ]

                    target.author = form.cleaned_data[
                        "author"
                    ]

                    target.initial_key = form.cleaned_data[
                        "initial_key"
                    ]

                    target.style = form.cleaned_data[
                        "style"
                    ]

                    target.style_other = form.cleaned_data.get(
                        "style_other",
                        "",
                    )

                    target.performing_forces = "solo"

                    target.voice_part = form.cleaned_data.get(
                        "voice_part",
                        "",
                    )

                    target.additional_comments = (
                        form.cleaned_data.get(
                            "additional_comments",
                            "",
                        )
                    )

                    # -----------------------------------------------------
                    # Clef information
                    # -----------------------------------------------------
                    target.written_clef_range = (
                        written_clef_range
                    )

                    target.clef_range = tess.clef_range

                    target.filename = new_filename

                    # -----------------------------------------------------
                    # Reset review status
                    # -----------------------------------------------------
                    target.status = "pending"
                    target.approval_at = None
                    target.approval_by = None
                    target.edited_at = timezone.now()
                    target.edited_by = request.user

                    # -----------------------------------------------------
                    # Tessitura
                    # -----------------------------------------------------
                    target.q1_freq = tess.lowFreq
                    target.q1_pitch = tess.lowNote
                    target.q1_octave = tess.lowOctave

                    target.q3_freq = tess.highFreq
                    target.q3_pitch = tess.highNote
                    target.q3_octave = tess.highOctave

                    target.median_freq = tess.median_freq

                    target.min_freq = tess.min_pitch
                    target.max_freq = tess.max_pitch

                    # -----------------------------------------------------
                    # Timing
                    # -----------------------------------------------------
                    target.cycle_dose = tess.cycle_dose
                    target.time_dose = tess.time_dose
                    target.rest_time = tess.rest_time
                    target.total_time = tess.total_time

                    # -----------------------------------------------------
                    # Passaggio values
                    # -----------------------------------------------------
                    target.hvhp_time_dose = (
                        passaggio.hvhp.time_dose
                    )
                    target.hvmp_time_dose = (
                        passaggio.hvmp.time_dose
                    )
                    target.hvlp_time_dose = (
                        passaggio.hvlp.time_dose
                    )

                    target.mvhp_time_dose = (
                        passaggio.mvhp.time_dose
                    )
                    target.mvmp_time_dose = (
                        passaggio.mvmp.time_dose
                    )
                    target.mvlp_time_dose = (
                        passaggio.mvlp.time_dose
                    )

                    target.lvhp_time_dose = (
                        passaggio.lvhp.time_dose
                    )
                    target.lvmp_time_dose = (
                        passaggio.lvmp.time_dose
                    )
                    target.lvlp_time_dose = (
                        passaggio.lvlp.time_dose
                    )

                    # -----------------------------------------------------
                    # Save MIDI
                    # -----------------------------------------------------
                    if uploaded_file:
                        # A new MIDI was uploaded, so replace the existing file.
                        if target.midi_file:
                            target.midi_file.delete(save=False)

                        with open(midi_path, "rb") as midi_f:
                            target.midi_file.save(
                                uploaded_file.name,
                                File(midi_f),
                                save=False,
                            )
                    elif not target.midi_file and record.midi_file:
                        # No new MIDI was uploaded, so preserve/copy the existing
                        # MIDI file if this is a newly created target record.
                        with record.midi_file.open("rb") as midi_f:
                            target.midi_file.save(
                                os.path.basename(record.midi_file.name),
                                File(midi_f),
                                save=False,
                            )

                    # -----------------------------------------------------
                    # Generate PDF
                    # -----------------------------------------------------
                    pdf = FPDF()

                    pdf.add_font(
                        "times_new",
                        "",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "B",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Bold.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "I",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Italic.ttf",
                            )
                        ),
                    )

                    pdf.add_font(
                        "times_new",
                        "BI",
                        utils.resource_path(
                            os.path.join(
                                "data",
                                "Times New Roman Bold Italic.ttf",
                            )
                        ),
                    )

                    pdf.add_page()

                    container = TessPassContainer(
                        tess,
                        passaggio,
                        target.title,
                        pdf,
                        output_dir=output_dir,
                        submitted_by=(
                            f"{record.submitted_by.first_name} "
                            f"{record.submitted_by.last_name}"
                            if record.submitted_by
                            else ""
                        ),
                    )

                    container.ensure_musescore_configured()
                    container.write_to_pdf()

                    pdf_filename = (
                        f"{safe_filename_part(record.title)}-"
                        f"{record.clef_range}-Tessituragram-"
                        f"{uuid.uuid4().hex[:8]}.pdf"
                    )

                    pdf_path = os.path.join(
                        work_dir,
                        pdf_filename,
                    )

                    pdf.output(pdf_path)

                    if target.pdf_file:
                        target.pdf_file.delete(
                            save=False
                        )

                    with open(pdf_path, "rb") as pdf_f:
                        target.pdf_file.save(
                            pdf_filename,
                            File(pdf_f),
                            save=False,
                        )

                    # -----------------------------------------------------
                    # Save record
                    # -----------------------------------------------------
                    target.save()

                return redirect(
                    "records:record_detail",
                    group_id=record.submission_group,
                )

            finally:
                shutil.rmtree(
                    work_dir,
                    ignore_errors=True,
                )

    else:
        form = ReviewerEditForm()

        form.initial["title"] = record.title
        form.initial["larger_work"] = record.larger_work
        form.initial["composer"] = record.composer
        form.initial["author"] = record.author
        form.initial["initial_key"] = record.initial_key
        form.initial["style"] = record.style
        form.initial["style_other"] = record.style_other
        form.initial["written_clef_range"] = record.written_clef_range
        form.initial["performing_forces"] = "solo"
        form.initial["voice_part"] = record.voice_part
        form.initial["additional_comments"] = record.additional_comments

        # Restore special choices if the existing record uses them.
        for field_name, value in (
            ("style", record.style),
            ("written_clef_range", record.written_clef_range),
        ):
            if value and value not in {
                choice_value
                for choice_value, _ in form.fields[field_name].choices
            }:
                form.fields[field_name].choices = list(
                    form.fields[field_name].choices
                ) + [(value, value)]

    return render(
        request,
        "submissions/edit_resubmit.html",
        {
            "form": form,
            "record": record,
            "current_midi_file": record.midi_file
        },
    )